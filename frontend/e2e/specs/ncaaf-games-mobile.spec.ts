import { expect, test } from "@playwright/test"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { collectPageErrors, mockApi, mockTeamLogos } from "../support/api-mock"
import { expectNoNaN, expectNoPageErrors } from "../support/assertions"

/**
 * NCAAF-P3.2 — the phone. Registered in the `mobile` project in `playwright.config.ts`.
 *
 * ⭐ WHY THIS IS ITS OWN FILE RATHER THAN MORE CLAUSES IN THE DESKTOP SPEC. The acceptance
 * criterion is "mobile-legible", and every defect in that class is INVISIBLE at 1280px: an SVG that
 * collapses, a three-column comparison that wraps into nonsense, a day strip that pushes the
 * document sideways. `tsc` and `next build` cannot see any of them, and neither can a desktop
 * assertion — NF-C6b's rollup was verified CORRECT on desktop and was unreadable on a phone, which
 * is the whole reason this project exists.
 *
 * ⭐ AND THE OVERFLOW CLAUSE MUST ASSERT THE SCROLLING CONTAINER'S OWN `scrollWidth`, NOT THE
 * PAGE'S (NF-C4). A day strip that scrolls inside its own `overflow-x-auto` box leaves the document
 * perfectly tidy — a page-level check would pass while the reader drags a table sideways, and it
 * would ALSO fail to distinguish "the strip scrolls, as designed" from "the strip broke the page".
 * So both are asserted, in opposite directions.
 */

const SLATE = JSON.parse(
  readFileSync(join(process.cwd(), "e2e", "fixtures", "api", "ncaaf-slate-2026-08-29.json"), "utf8"),
)

const PATH = "/ncaaf/games"

test("the page never scrolls sideways on a phone", async ({ page }) => {
  const errors = collectPageErrors(page)
  await mockApi(page, { ncaafSlate: "mixed" }) // the widest variant: three populated columns
  await page.goto(PATH)
  await expect(page.getByTestId("ncaaf-game-card").first()).toBeVisible()

  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  // A pixel of rounding is tolerable; a column pushed off-screen is not.
  expect(scrollWidth, `document scrollWidth ${scrollWidth} vs viewport ${clientWidth}`)
    .toBeLessThanOrEqual(clientWidth + 1)

  await expectNoNaN(page)
  expectNoPageErrors(errors)
})

test("the day strip scrolls inside its OWN box, not the document's", async ({ page }) => {
  // The positive half of the clause above: the strip is allowed — required — to be scrollable, and
  // a build that made it wrap instead would silently change the control's behaviour without
  // failing the page-level check.
  await mockApi(page, {
    // A long season's worth of days, so the strip genuinely overflows a 412px phone. Derived from
    // the captured manifest so every other field stays production's.
    transform: (pathname, body) =>
      pathname === "/ncaaf/manifest"
        ? {
            ...body,
            game_days: Array.from({ length: 16 }, (_, i) => ({
              game_day: `2026-09-${String(i + 5).padStart(2, "0")}`,
              n_games: 30,
            })),
          }
        : body,
    ncaafSlate: "empty",
  })
  await page.goto(PATH)
  const strip = page.getByTestId("ncaaf-day-picker").locator("div").filter({ has: page.getByTestId("ncaaf-day-option") }).first()
  await expect(strip).toBeVisible()
  const box = await strip.evaluate((el) => ({
    scrollWidth: el.scrollWidth,
    clientWidth: el.clientWidth,
    overflowX: getComputedStyle(el).overflowX,
  }))
  expect(box.overflowX).toBe("auto")
  expect(box.scrollWidth).toBeGreaterThan(box.clientWidth)

  const doc = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  expect(doc.scrollWidth).toBeLessThanOrEqual(doc.clientWidth + 1)
})

test("both curves render at a readable height on a phone", async ({ page }) => {
  // An SVG whose container collapses to zero renders as an invisible nothing that still passes
  // every text assertion on the card — the exact failure `ResponsiveContainer` produces and the
  // reason this component is a hand-rolled `viewBox`'d `<svg>`.
  await mockApi(page)
  await page.goto(PATH)
  const c = page.locator(`[data-testid="ncaaf-game-card"][data-game-id="${SLATE.games[0].game_id}"]`)
  for (const which of ["margin", "total"]) {
    const svg = c.getByTestId(`ncaaf-curve-${which}`).locator("svg")
    const box = await svg.boundingBox()
    expect(box, `${which} curve did not render a box`).not.toBeNull()
    expect(box!.height).toBeGreaterThan(60)
    expect(box!.width).toBeGreaterThan(180)
  }
})

test("the win probability stays the biggest thing on the card at phone width", async ({ page }) => {
  // The brand directive's lead clause has to survive the viewport where the card is most crowded.
  await mockApi(page, { ncaafSlate: "mixed" })
  await page.goto(PATH)
  const c = page.getByTestId("ncaaf-game-card").first()
  // ⚠️ Wait for the panel BEFORE measuring. `evaluateAll` does not auto-retry, and an under-collected
  // size list would make this clause pass more easily rather than fail — a weaker test that still
  // looks green, which is the harder kind of vacuity to notice.
  await expect(c.getByTestId("ncaaf-market-comparison")).toBeVisible()
  const prob = await c
    .getByTestId("ncaaf-win-probability-home")
    .evaluate((el) => parseFloat(getComputedStyle(el).fontSize))
  const sizes = await c
    .locator("h3, [data-testid='ncaaf-market-comparison'] span")
    .evaluateAll((els) => els.map((e) => parseFloat(getComputedStyle(e).fontSize)))
  expect(prob).toBeGreaterThan(Math.max(...sizes))
})

/** A height that has stopped moving.
 *
 * ⚠️ TWO things make a single `boundingBox()` unreliable here, and they are different. (1) Radix
 * unmounts the accordion content a frame after `data-expanded` flips, so a read taken on the
 * attribute is early. (2) ⭐ WEB FONTS: measured across four runs the same collapsed slate reported
 * 2288 / 2531 / 2797px — a 20% spread — because fallback metrics differ from the loaded face. A
 * layout assertion taken before `document.fonts.ready` is measuring the fallback font. */
async function settledHeight(page: import("@playwright/test").Page, testId: string): Promise<number> {
  await page.evaluate(() => document.fonts.ready)
  const el = page.getByTestId(testId)
  let last = -1
  for (let i = 0; i < 25; i++) {
    const h = (await el.boundingBox())!.height
    if (Math.abs(h - last) < 1) return h
    last = h
    await page.waitForTimeout(80)
  }
  return last
}

test("collapsing actually reclaims the height it exists to reclaim, on a phone", async ({ page }) => {
  // ⭐ THE CLAUSE THAT TESTS THE POINT, NOT THE MECHANISM. Everything else about collapsing can be
  // asserted at any viewport — that a class toggles, that a node disappears. The REASON it was
  // built is that one expanded card is more than a phone viewport, so an eight-game slate is eight
  // scrolls before a reader has seen the slate. So this measures the thing that was wrong: the
  // rendered HEIGHT of the list, at a phone width, before and after.
  //
  // ⚠️ The bar is a RATIO, not a pixel count. A pixel expectation would be a second copy of the
  // card's layout, red on any spacing change; the claim is "materially shorter", so that is what
  // is asserted.
  await mockApi(page)
  await page.goto(PATH)
  await expect(page.getByTestId("ncaaf-game-card")).toHaveCount(SLATE.games.length)

  const expandedHeight = await settledHeight(page, "ncaaf-game-list")
  const viewport = page.viewportSize()!.height
  // The premise, measured rather than assumed — if a card ever became short enough that collapsing
  // stopped mattering, this clause should say so instead of quietly passing.
  expect(
    expandedHeight / SLATE.games.length,
    `an expanded card is ${Math.round(expandedHeight / SLATE.games.length)}px against a ${viewport}px viewport`,
  ).toBeGreaterThan(viewport * 0.6)

  await page.getByTestId("ncaaf-toggle-all").click()
  await expect(page.getByTestId("ncaaf-game-card").first()).toHaveAttribute("data-expanded", "false")
  const collapsedHeight = await settledHeight(page, "ncaaf-game-list")

  expect(
    collapsedHeight,
    `collapsed ${Math.round(collapsedHeight)}px vs expanded ${Math.round(expandedHeight)}px`,
  ).toBeLessThan(expandedHeight * 0.5)
  // ⚠️ PER CARD, NOT PER SLATE. The first cut bounded the whole list against three viewports, which
  // is a bar that depends on how many games are on the board — fine for an 8-game opener, absurd
  // for a 60-game October Saturday, so it would have had to be relaxed later for a reason that has
  // nothing to do with this component. "At least two collapsed cards fit on a screen" is the claim
  // that actually holds whatever the slate size.
  expect(
    collapsedHeight / SLATE.games.length,
    `a collapsed card is ${Math.round(collapsedHeight / SLATE.games.length)}px of a ${viewport}px viewport`,
  ).toBeLessThan(viewport * 0.5)
  // Recorded rather than only asserted: the ratio is the claim, and a future reader wants the
  // numbers this ran on, not a bar someone once chose.
  test.info().annotations.push({
    type: "collapse-height",
    description:
      `viewport ${viewport}px · expanded ${Math.round(expandedHeight)}px ` +
      `(${(expandedHeight / viewport).toFixed(1)} screens, ${Math.round(expandedHeight / SLATE.games.length)}px/card) · ` +
      `collapsed ${Math.round(collapsedHeight)}px ` +
      `(${(collapsedHeight / viewport).toFixed(1)} screens, ${Math.round(collapsedHeight / SLATE.games.length)}px/card) · ` +
      `${Math.round(100 - (100 * collapsedHeight) / expandedHeight)}% shorter`,
  })


  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  expect(scrollWidth, "collapsing must not push the document sideways").toBeLessThanOrEqual(clientWidth + 1)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// NCAAF-P3.9 — the phone half of the nav door, and the phone half of the logo constraint
// ══════════════════════════════════════════════════════════════════════════════════════════════

/** ⚠️ Scoped to `[data-primary-nav]` and `:visible`. `SiteFooter` wraps its columns in `<nav>` (the
 *  collision this repo has hit four times), and `:visible` rather than `.first()` because the
 *  desktop bar renders its OWN copy of this door with `hidden … sm:block` and comes FIRST in the
 *  DOM — `.first()` would resolve to an element correctly hidden at 412px and fail on the wrong
 *  node, which is the exact mistake `positioning-alignment.spec.ts` records for its FAQ clause. */
const phoneNavEntry = (page: import("@playwright/test").Page) =>
  page.locator('[data-primary-nav] [data-nav-item="ncaaf-games"]:visible')

test("the NCAAF door is reachable from the phone menu, not only from the desktop bar", async ({
  page,
}) => {
  await mockApi(page)
  await mockTeamLogos(page)
  // From a page that is NOT the board — the requirement is that a stranger can FIND the surface.
  await page.goto("/about")

  // The desktop bar's links are `hidden sm:block`, so at this width the hamburger is the only nav
  // there is. E9.58's second defect was exactly this shape: an affordance that existed at every
  // viewport except the one most first-touch readers arrive on.
  await expect(
    phoneNavEntry(page),
    "the NCAAF door is visible before the phone menu is opened — the bar links should be hidden here",
  ).toHaveCount(0)

  await page.getByRole("button", { name: /toggle menu/i }).click()
  const entry = phoneNavEntry(page)
  await expect(entry, "no NCAAF door in the signed-out phone menu").toHaveCount(1)

  await entry.click()
  await page.waitForURL(/\/ncaaf\/games$/)
  await expect(page.getByTestId("ncaaf-game-card").first()).toBeVisible()
})

test("the phone menu marks the NCAAF door current while standing on the board", async ({ page }) => {
  await mockApi(page)
  await mockTeamLogos(page)
  await page.goto(PATH)
  await page.getByRole("button", { name: /toggle menu/i }).click()
  await expect(phoneNavEntry(page)).toHaveAttribute("data-nav-active", "true")
})

test("the team marks stay smaller than the win probability on a phone", async ({ page }) => {
  // ⭐ THE BRAND DIRECTIVE'S LEAD CLAUSE, EXTENDED TO A NON-TEXT ELEMENT. The existing clause above
  // compares FONT SIZES, which an image cannot have — so a logo could grow to dominate the card
  // without moving that assertion by a pixel. This measures the RENDERED BOX, which is the only
  // comparison that can hold between an image and a number.
  await mockApi(page, { ncaafSlate: "mixed" }) // the most crowded card
  await mockTeamLogos(page)
  await page.goto(PATH)
  const c = page.getByTestId("ncaaf-game-card").first()
  await expect(c.getByTestId("ncaaf-market-comparison")).toBeVisible()

  const prob = (await c.getByTestId("ncaaf-win-probability-home").boundingBox())!
  const logoBoxes = await c
    .getByTestId("ncaaf-team-logo")
    .evaluateAll((els) => els.map((e) => e.getBoundingClientRect().height))
  expect(logoBoxes.length, "no logos rendered — this clause would be vacuous").toBeGreaterThan(0)
  expect(
    Math.max(...logoBoxes),
    `a team mark is ${Math.max(...logoBoxes)}px against a ${prob.height}px probability`,
  ).toBeLessThan(prob.height)
})

test("a failed logo moves nothing on the card", async ({ page }) => {
  // ⭐ "DECORATIVE ONLY — no layout shift that moves the probability or curves" is a claim about a
  // DIFFERENCE, so it is measured as one: the SAME card, rendered with the marks loaded and then
  // with the CDN refused, must put the probability and the curve in the same place. A single-state
  // assertion could not see a fallback that occupied a different box, which is the ordinary way
  // this goes wrong — and it is why the component shares one size string between both branches.
  await mockApi(page)
  await mockTeamLogos(page)
  await page.goto(PATH)

  const card = page.getByTestId("ncaaf-game-card").first()
  // ⚠️ Fonts settle before ANY layout read. Measured across four runs the same slate reported a 20%
  // height spread against fallback metrics (see `settledHeight` above), which would swamp a 20px
  // logo either way — the difference this clause is looking for is smaller than the noise it would
  // otherwise be measuring.
  const geometry = async () => {
    await page.evaluate(() => document.fonts.ready)
    const prob = (await card.getByTestId("ncaaf-win-probability-home").boundingBox())!
    const curve = (await card.getByTestId("ncaaf-curve-margin").boundingBox())!
    return { probY: prob.y, probH: prob.height, curveY: curve.y }
  }

  await expect(card.getByTestId("ncaaf-team-logo").first()).toBeVisible()
  const loaded = await geometry()

  // A NEWER handler wins in Playwright, so this replaces the fulfilling route with an aborting one
  // without tearing down the API mock underneath it.
  await mockTeamLogos(page, { broken: true })
  await page.reload()
  await expect(card.getByTestId("ncaaf-team-logo-fallback").first()).toBeVisible()
  await expect(card.getByTestId("ncaaf-team-logo")).toHaveCount(0)
  const failed = await geometry()

  expect(failed.probY, "a failed logo moved the win probability").toBeCloseTo(loaded.probY, 0)
  expect(failed.probH).toBeCloseTo(loaded.probH, 0)
  expect(failed.curveY, "a failed logo moved the margin curve").toBeCloseTo(loaded.curveY, 0)
})
