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
 * ⚠️ BOTH FIXTURES' CONTENT CHANGES UNDER US. `picks-featured.json` is a different game every day;
 * `fantasy-nfl-featured-player.json` is a different player whenever the board is re-published. So
 * every assertion here reads the payload's OWN values rather than a literal — a spec pinned to
 * "CIN @ WSH" or "George Kittle" would go red on a re-capture and teach everyone to re-capture less
 * often.
 *
 * ⚠️ CORRECTED 2026-08-08 — the first cut of this file described the MLB pick as "today's widest
 * model-vs-market gap". It is not, and the copy that said so shipped. The serving query filters on
 * `layer4_h2h_conviction_flag` (two independent Credence estimators agreeing within 0.02, computed
 * without reference to odds) and then orders `game_datetime ASC … LIMIT 1` — the EARLIEST-STARTING
 * qualifying game. Nothing in the selection looks at the size of the gap.
 */

const PLAYER = FIXTURES.featuredFantasyPlayer() as {
  player: { name: string; pos: string; team: string; headshot: string }
  projection: { ptsStd: number; ptsHalf: number; ptsPpr: number; p10: number; p90: number; games: number }
  market: { adp: number; adpRank: number; ourRank: number; rankGap: number }
  drivers: { feature: string; label: string; pts: number }[]
  leanNote: string
}

const PICK = FIXTURES.featuredPick() as {
  game_pk: number | null
  matchup: string
  edge: number
  model_prob: number
  market_prob: number
  pick_date: string
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

/** Also wait for the fantasy card, which is a SECOND independent fetch. Kept separate from
 *  `gotoHome` because several specs deliberately fail or empty ONE of the two reads and must not
 *  wait on the block they just broke. */
async function gotoHomeWithFantasy(page: Page) {
  await gotoHome(page)
  await expect(page.locator("#fantasy-proof").getByText(PLAYER.player.name)).toBeVisible()
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

test("a carried-over read announces itself as a previous day's, not today's", async ({ page }) => {
  // ⭐ THE THIRD STATE, added when the operator asked for the previous read to stay up until the
  // morning run publishes (2026-08-08). It is the one state of the four that can state something
  // FALSE about a live slate: empty and failed both describe themselves accurately, but a
  // yesterday card rendered as today's read shows a probability for a game that has already been
  // played. So the assertion is not "the note exists" — it is that the note and the date agree,
  // and that nothing on the card claims to be today.
  const errors = collectPageErrors(page)
  const mock = await mockApi(page, {
    // `is_stale: true` is exactly what the API returns when today's run has not published and the
    // carry-over query resolved the previous read. `yesterday` is dropped alongside it because the
    // card IS yesterday — serving both would show the same day twice under two labels.
    transform: (path, body) =>
      path === "/picks/featured" ? { ...body, is_stale: true, yesterday: null } : body,
  })
  await gotoHome(page)

  const block = page.locator("#today")
  await expect(block.getByText(/hasn't published yet/i)).toBeVisible()
  await expect(block.getByText(/not today's slate/i)).toBeVisible()

  // The date the note points at ("the date shown above") has to actually be on screen, or the
  // sentence is a dangling reference. PICK.pick_date is an ISO date; the card renders it long-form.
  const d = new Date(PICK.pick_date + "T12:00:00")
  const long = d.toLocaleDateString("en-US", { month: "long", day: "numeric" })
  await expect(block.getByText(long)).toBeVisible()

  // ⛔ AND THE CARD IS STILL THERE. A carry-over that blanked the numbers would satisfy any
  // "does it say it is stale" check while delivering the empty page this change exists to avoid.
  await expect(block.getByText(PICK.matchup)).toBeVisible()
  await expect(
    block.getByText(/Nothing to show yet/i),
    "the carry-over collapsed into the empty state",
  ).toHaveCount(0)

  expectApiFullyMocked(mock)
  await expectNoNaN(page)
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

  const mlbTrust = page.getByRole("link", { name: /grade out/i }).first()
  await expect(mlbTrust).toBeVisible()
  expect(await mlbTrust.getAttribute("href")).toBe("/performance")

  // ⭐ THE ASYMMETRY MUST BE VISIBLE, IN BOTH DIRECTIONS. `/fantasy/track-record` is genuinely
  // public; every MLB record endpoint (`/picks/scorecard`, `/performance`, `/picks/today`,
  // `/picks/history`) returns 401 to an anonymous request — verified 2026-08-08. Sending a stranger
  // from a TRUST link into a login wall unannounced is the one surprise a trust link cannot afford,
  // so the free one says free and the gated one says members.
  await expect(page.getByText(/free, no account/i).first()).toBeVisible()
  await expect(
    page.locator('[data-vertical="betting"]').getByText(/members/i),
    "the MLB record link does not disclose that it needs an account",
  ).toBeVisible()
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

  // And the positive half: the quantity is named as a DIFFERENCE, not as an advantage we hold.
  //
  // ⚠️ SCOPED TO THE STAT CHIPS BY `data-stat`, and the reason is a genuine collision between two
  // rules rather than a locator preference. The block now legitimately contains the word "edge" —
  // "Daily edge, quantified" is the MLB product's own retired-H1 tagline, kept here on purpose —
  // so "no 'edge' anywhere in #today" would fail on copy that is meant to be there. What must stay
  // true is narrower and is the thing that would actually mislead: no STAT is labelled Edge.
  const statLabels = await page
    .locator("#today [data-stat]")
    .evaluateAll((els) => els.map((e) => (e.textContent ?? "").toLowerCase()))
  expect(statLabels.length, "no stat chips found — this assertion would be vacuous").toBeGreaterThan(2)
  expect(
    statLabels.filter((l) => /\bedge\b/.test(l)),
    "a model-vs-market stat is labelled 'edge' — on a marketing page that reads as a claim to have " +
      "one, and `best_alpha = 0` says we do not",
  ).toEqual([])
  expect(
    statLabels.some((l) => /\bgap\b/.test(l)),
    "the model-vs-market difference is not labelled 'Gap' anywhere",
  ).toBe(true)
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
  // ⚠️ NO DATES. "Around Aug 29" is a promise a visitor can check and find false on the day;
  // "coming this season" is a commitment we control. Asserted two-sided so a date cannot creep back.
  await expect(page.getByText(/Coming this season/i).first()).toBeVisible()
  const roadmapText = await page.locator("ul", { hasText: "Coming this season" }).first().innerText()
  expect(roadmapText, "a dated launch promise is back on the roadmap").not.toMatch(
    /\b(Aug|Sep|September|August)\s*\d/i,
  )
  // The un-shipped rows are the SAME product as the live MLB one, not a different, better one.
  expect(roadmapText).toMatch(/Betting intelligence/i)
  expect(roadmapText, "the roadmap still calls the NFL row a 'game model'").not.toMatch(/game model/i)

  // ⛔ E9.56c's dead `/pricing` CTA wearing a friendlier label. `route-integrity.spec.ts` would
  // catch a 404 target; it would NOT catch a link to a real-but-empty surface teased as live, so
  // the rule enforced here is that an un-shipped row carries no anchor at all.
  const roadmapRow = page.locator("li", { hasText: "Coming this season" }).first()
  expect(await roadmapRow.locator("a").count(), "a coming-soon row is a link").toBe(0)

  // The sentence that keeps the roadmap from promising results it has no basis to promise.
  //
  // ⚠️ ITS WORDING IS CONSTRAINED BY THE DENYLIST, WHICH IS WORTH KNOWING BEFORE EDITING IT. The
  // first draft read "not a promise of picks that win" — a NEGATION, and still a red build, because
  // a substring scan cannot see the "not". Any rewrite has to avoid the denied phrases outright
  // rather than disclaim them.
  await expect(page.getByText(/analysis rather than an assurance of results/i)).toBeVisible()
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// AC 7 — the FANTASY product proof, and it comes FIRST
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("the fantasy proof renders a real player from the served board", async ({ page }) => {
  const errors = collectPageErrors(page)
  const mock = await mockApi(page)
  await gotoHomeWithFantasy(page)

  const card = page.locator("#fantasy-proof")

  // ⭐ FOLLOWS THE SERVER, the E9.59 rule: "a card renders" and "the SERVED card renders" are
  // different assertions, and only the second can tell live data from a hand-built mock-up.
  await expect(card.getByText(PLAYER.player.name)).toBeVisible()
  await expect(
    card.getByText(`${PLAYER.player.pos}${PLAYER.market.ourRank}`, { exact: false }).first(),
  ).toBeVisible()
  await expect(
    card.getByText(`${PLAYER.player.pos}${PLAYER.market.adpRank}`, { exact: false }).first(),
  ).toBeVisible()

  // The imagery the operator asked for, asserted as real elements rather than as layout.
  await expect(card.locator(`img[src="${PLAYER.player.headshot}"]`)).toBeVisible()
  await expect(
    card.locator('img[src*="espncdn.com/i/teamlogos/nfl"]'),
    "no NFL team logo on the fantasy card",
  ).toBeVisible()

  // Projection, its range, and the availability figure that makes the points legible.
  const cardText = await card.innerText()
  expect(cardText).toContain(PLAYER.projection.ptsPpr.toFixed(1))
  expect(cardText).toContain(PLAYER.projection.games.toFixed(1))
  expect(cardText, "the 80% range is missing").toMatch(
    new RegExp(`${Math.round(PLAYER.projection.p10)}\\s*–\\s*${Math.round(PLAYER.projection.p90)}`),
  )

  // The drivers — the "what is moving this" the operator asked for, from real transparency data.
  for (const d of PLAYER.drivers) {
    await expect(card.getByText(d.label, { exact: false }).first()).toBeVisible()
  }

  expectApiFullyMocked(mock)
  await expectNoNaN(page)
  expectNoPageErrors(errors)
})

test("⭐ personalisation is SHOWN, not asserted — one player, three formats", async ({ page }) => {
  // "Built for your league, not a generic one" is a claim until a visitor watches the same
  // player's season total move with the scoring rules. All three come off one payload, so a card
  // that rendered only the PPR number would be describing the benefit instead of demonstrating it.
  await mockApi(page)
  await gotoHomeWithFantasy(page)

  const card = page.locator("#fantasy-proof")
  const text = await card.innerText()
  for (const pts of [PLAYER.projection.ptsStd, PLAYER.projection.ptsHalf, PLAYER.projection.ptsPpr]) {
    expect(text, `the ${pts} format scoring is missing`).toContain(pts.toFixed(1))
  }
  // Distinct numbers, or the demonstration proves nothing.
  expect(new Set([PLAYER.projection.ptsStd, PLAYER.projection.ptsHalf, PLAYER.projection.ptsPpr]).size)
    .toBeGreaterThan(1)
  await expect(card.getByText(/Standard/i).first()).toBeVisible()
  await expect(card.getByText(/Half-PPR/i).first()).toBeVisible()
})

test("⛔ the rank gap never ships without its market-lean caveat", async ({ page }) => {
  // Measured on the live artifact: ZERO of the 111 players eligible for this card carry
  // `mktLean == "independent"` — that value is exactly the thin-data rookie case with no drivers.
  // So our ranking always blends market consensus at the positions we can feature, and a card that
  // showed the gap without saying so would overstate what the gap means.
  await mockApi(page)
  await gotoHomeWithFantasy(page)

  const card = page.locator("#fantasy-proof")
  // Rendered inline, NOT behind a disclosure — a caveat a visitor has to open is a caveat most of
  // them never read, and this one qualifies the headline number on the card.
  await expect(card.getByText(PLAYER.leanNote.slice(0, 60), { exact: false })).toBeVisible()
})

test("the fantasy card states the DIRECTION of the disagreement in words", async ({ page }) => {
  // The selection is not constrained to a flattering direction — today's live winner is a player
  // we rank LOWER than the market drafts him. A coloured arrow alone would read as a verdict, so
  // the card says which way it goes.
  await mockApi(page)
  await gotoHomeWithFantasy(page)

  const text = await page.locator("#fantasy-proof").innerText()
  const expected = PLAYER.market.rankGap > 0 ? /ranks? him .* higher/i : /ranks? him .* lower/i
  expect(text, "the card does not say which way the disagreement runs").toMatch(expected)
})

test("⭐ the FANTASY proof comes before the MLB proof", async ({ page }) => {
  // The acquisition-priority ordering (operator, 2026-08-08), asserted geometrically because that
  // is what "comes first" means to a visitor. A source-order check would pass on a page whose CSS
  // reordered them.
  await mockApi(page)
  await gotoHomeWithFantasy(page)

  const fantasyTop = await topOf(page.locator("#fantasy-proof"))
  const mlbTop = await topOf(page.locator("#today"))
  expect(
    fantasyTop,
    "the MLB card renders above the fantasy card — fantasy is the acquisition priority and must " +
      "be the first substantive product demonstration",
  ).toBeLessThan(mlbTop)
})

test("a failed fantasy read hides the card without touching the rest of the page", async ({
  page,
}) => {
  const errors = collectPageErrors(page)
  await mockApi(page, { fail: ["/fantasy/nfl/featured-player"] })
  await gotoHome(page)

  await expect(page.locator("#fantasy-proof")).toHaveCount(0)
  // ⭐ AND EVERYTHING ELSE SURVIVES. The two live blocks are independent reads; one failing must
  // not take the positioning, the other product's proof, or the CTAs with it.
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
  await expect(page.locator('[data-vertical="fantasy"]')).toBeVisible()
  await expect(page.locator("#today")).toBeVisible()
  expectNoPageErrors(errors)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// AC 8 — the MLB badge says what was actually measured
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("⛔ the MLB card never says HIGH CONVICTION", async ({ page }) => {
  // ⭐ THE SERVED `conviction_label` IS A HARDCODED CONSTANT — the literal string "HIGH CONVICTION",
  // stamped on every featured pick in both the serving writer and the API fallback. It classifies
  // nothing, and a bettor reads it as "we are confident this team wins", which is precisely the
  // claim `best_alpha = 0` forbids.
  await mockApi(page)
  await gotoHome(page)

  const text = await renderedText(page)
  expect(text, "the hardcoded conviction label is being rendered").not.toMatch(/high conviction/i)
})

test("the badge describes the model agreement it is actually derived from", async ({ page }) => {
  // What the row satisfies is `|calibrated_win_prob − P(run_diff > 0)| ≤ 0.02` — two INDEPENDENT
  // Credence estimators agreeing with each other, computed without reference to the odds. So the
  // badge is a statement about our models, and the popover keeps it from being read as a promise
  // about the result or a claim about the market.
  await mockApi(page)
  await gotoHome(page)

  const block = page.locator("#today")
  await expect(block.getByText(/our models agree/i)).toBeVisible()

  await block.getByRole("button", { name: /what our models agreeing means/i }).click()
  const hint = await renderedText(page)
  expect(hint).toMatch(/independent/i)
  expect(hint, "the badge's explanation does not disclaim a market judgement").toMatch(
    /says nothing about whether the market is wrong/i,
  )
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// AC 9 — the MLB record is described accurately: graded daily, and behind an account
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("the page says the record exists AND that no durable advantage has been shown", async ({
  page,
}) => {
  // ⭐ BOTH HALVES, AND THEY PULL AGAINST EACH OTHER. Copy implying we do not measure ourselves
  // would be as false as copy claiming an edge — the daily model-vs-market record is real, graded,
  // and a genuine part of the product. What it has not shown is a durable advantage over the
  // closing market. Dropping either half is a different kind of dishonest.
  await mockApi(page)
  await gotoHome(page)

  const text = await renderedText(page)
  expect(text, "the page never says the picks are graded against the market").toMatch(
    /graded against the market/i,
  )
  expect(text, "the page never states the limit of what the record has shown").toMatch(
    /durable advantage/i,
  )
})

test("the record is described as members-only, never as public", async ({ page }) => {
  // ⚠️ VERIFIED 2026-08-08: /picks/scorecard, /performance, /picks/today and /picks/history all
  // return 401 to an anonymous request. Copy calling the MLB record "public" would send a cold
  // visitor into a login wall from the one link that must not surprise them.
  await mockApi(page)
  await gotoHome(page)

  const text = await renderedText(page)
  expect(text, "the MLB record is advertised as public, but every record endpoint 401s").not.toMatch(
    /public (daily )?(track )?record/i,
  )
  expect(text).toMatch(/members' scorecard/i)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// AC 10 — the hero carries the new positioning, and the old H1 is scoped to MLB
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("the hero leads with the platform positioning", async ({ page }) => {
  await mockApi(page)
  await gotoHome(page)

  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    /The number is only half the answer/i,
  )
  const text = await renderedText(page)
  expect(text).toMatch(/Betting intelligence · Fantasy decision tools/i)
})

test('"Daily edge, quantified" is MLB product language, never the company headline', async ({
  page,
}) => {
  // It was the site's H1 until this release, from when Credence was one product. Keeping it as the
  // betting product's tagline is deliberate; letting it drift back up into the hero is the
  // regression, because it does not span a company that now ships fantasy too.
  await mockApi(page)
  await gotoHome(page)

  const h1 = await page.getByRole("heading", { level: 1 }).innerText()
  expect(h1, "the retired tagline is back as the company H1").not.toMatch(/daily edge/i)

  const mlbBlock = await page.locator("#today").innerText()
  expect(mlbBlock, "the MLB product tagline is not on the MLB block").toMatch(/daily edge/i)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// AC 11 — the methodology section carries the positioning it proves
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("the trust section is headed by the claim its four principles prove", async ({ page }) => {
  await mockApi(page)
  await gotoHome(page)

  const heading = page.getByRole("heading", {
    name: /Sports models that admit what they don't know/i,
  })
  await expect(heading).toBeVisible()

  // The four cells ARE the evidence, so they must render below the claim rather than anywhere else.
  const headingTop = await topOf(heading)
  for (const principle of [
    /We show the uncertainty/i,
    /We grade ourselves in public/i,
    /We show our inputs/i,
    /We retire what fails/i,
  ]) {
    const cell = page.getByText(principle).first()
    await expect(cell).toBeVisible()
    expect(await topOf(cell)).toBeGreaterThan(headingTop)
  }
})

test("⛔ no synthetic-validation capability is advertised before it ships", async ({ page }) => {
  // Advertising roadmap work as shipped capability is the same defect class as a coming-soon link
  // into a route that does not exist — on the one section whose subject is our standard of
  // evidence, which makes it worse rather than better.
  await mockApi(page)
  await gotoHome(page)

  const text = await renderedText(page)
  for (const unshipped of [/SIM-V1/i, /synthetic validation/i, /stress-test the (models|gates)/i]) {
    expect(text, `an unshipped capability is advertised: ${unshipped}`).not.toMatch(unshipped)
  }
})
