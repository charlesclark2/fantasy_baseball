import { expect, test } from "@playwright/test"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { collectPageErrors, mockApi } from "../support/api-mock"
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
  await mockApi(page, { ncaafSlate: "market" }) // the widest variant: three populated columns
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
  await mockApi(page, { ncaafSlate: "market" })
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
  const list = page.getByTestId("ncaaf-game-list")
  await expect(page.getByTestId("ncaaf-game-card")).toHaveCount(SLATE.games.length)

  const expandedHeight = (await list.boundingBox())!.height
  const viewport = page.viewportSize()!.height
  // The premise, measured rather than assumed — if a card ever became short enough that collapsing
  // stopped mattering, this clause should say so instead of quietly passing.
  expect(
    expandedHeight / SLATE.games.length,
    `an expanded card is ${Math.round(expandedHeight / SLATE.games.length)}px against a ${viewport}px viewport`,
  ).toBeGreaterThan(viewport * 0.6)

  await page.getByTestId("ncaaf-toggle-all").click()
  await expect(page.getByTestId("ncaaf-game-card").first()).toHaveAttribute("data-expanded", "false")
  const collapsedHeight = (await list.boundingBox())!.height

  expect(
    collapsedHeight,
    `collapsed ${Math.round(collapsedHeight)}px vs expanded ${Math.round(expandedHeight)}px`,
  ).toBeLessThan(expandedHeight * 0.5)
  // ...and the whole slate now fits in a couple of screens rather than eight.
  expect(collapsedHeight).toBeLessThan(viewport * 3)
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
