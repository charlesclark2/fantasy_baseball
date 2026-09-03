import { expect, test } from "@playwright/test"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { collectPageErrors, mockApi, mockTeamLogos } from "../support/api-mock"
import { expectNoNaN, expectNoPageErrors } from "../support/assertions"

/**
 * NCAAF-P3.3 — the team page on a phone. Registered in the `mobile` project.
 *
 * ⭐ WHY ITS OWN FILE, and it is the same argument `ncaaf-games-mobile.spec.ts` makes: every defect
 * in this class is INVISIBLE at 1280px. This page is denser than the game board — a six-column
 * stat grid, a three-column adjusted/raw table, and a schedule row carrying a date, a venue marker,
 * an opponent, tags, a score and a link — so the phone is where it either wraps into something
 * legible or pushes the document sideways.
 *
 * ⭐ AND THE OVERFLOW CLAUSE ASSERTS BOTH DIRECTIONS (NF-C4). A table that scrolls inside its own
 * `overflow-x-auto` box leaves the DOCUMENT perfectly tidy, so a page-level check alone would pass
 * while a reader drags content sideways. The page must not scroll; a container that is meant to may.
 */

const FIXTURE_DIR = join(process.cwd(), "e2e", "fixtures", "api")
const readFixture = (name: string) => JSON.parse(readFileSync(join(FIXTURE_DIR, name), "utf8"))
const TEAM_POPULATED = readFixture("ncaaf-team-populated.synthetic.json")

const PATH = "/ncaaf/teams/68"

test("the team page never scrolls sideways on a phone", async ({ page }) => {
  const errors = collectPageErrors(page)
  // The POPULATED payload deliberately: it is the widest variant this page can render, with every
  // block present and the stat grids at full occupancy. A captured 2026 team has two empty blocks
  // and would leave the densest layout untested.
  await mockApi(page, { ncaafTeam: "populated" })
  await mockTeamLogos(page)
  await page.goto(PATH)
  await expect(page.getByTestId("ncaaf-team-header")).toBeVisible()

  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  expect(scrollWidth, `the document is ${scrollWidth}px wide in a ${clientWidth}px viewport`)
    .toBeLessThanOrEqual(clientWidth + 1)
  expectNoPageErrors(errors)
  await expectNoNaN(page)
})

test("the rating and its band are both legible at phone width", async ({ page }) => {
  // ⭐⭐ THE PAGE'S CENTRAL CLAIM HAS TO SURVIVE THE NARROWEST VIEWPORT. The band is not an
  // adornment on the rating — it is half the number — so a layout that pushed it off-screen, or
  // shrank it to the point of being unreadable, would turn an uncertainty-first page into a
  // point-prediction one at exactly the width most readers use.
  await mockApi(page, { ncaafTeam: "populated" })
  await page.goto(PATH)

  const rating = page.getByTestId("ncaaf-strength-rating")
  const band = page.getByTestId("ncaaf-strength-band")
  await expect(rating).toBeVisible()
  await expect(band).toBeVisible()

  const viewport = page.viewportSize()!
  for (const [name, loc] of [["rating", rating], ["band", band]] as const) {
    const box = (await loc.boundingBox())!
    expect(box, `${name} has no box`).toBeTruthy()
    expect(box.x, `${name} starts off-screen`).toBeGreaterThanOrEqual(0)
    expect(box.x + box.width, `${name} runs past the viewport`).toBeLessThanOrEqual(viewport.width + 1)
  }
  // The band's text must not be shrunk into illegibility beside the big rating.
  const bandFont = await band.evaluate((el) => parseFloat(getComputedStyle(el).fontSize))
  expect(bandFont, `the band renders at ${bandFont}px`).toBeGreaterThanOrEqual(12)
})

test("the adjusted/raw table stays inside the page on a phone", async ({ page }) => {
  // Three columns of numbers plus a long row label is the widest thing on this page. If it scrolls
  // it must scroll inside ITS OWN box; if it does not, its content must fit.
  await mockApi(page, { ncaafTeam: "populated" })
  await page.goto(PATH)
  const row = page.getByTestId("ncaaf-efficiency-off-ppa")
  await expect(row).toBeVisible()
  const { scrollWidth, clientWidth } = await row.evaluate((el) => ({
    scrollWidth: el.scrollWidth,
    clientWidth: el.clientWidth,
  }))
  expect(scrollWidth, "an efficiency row overflows its own box").toBeLessThanOrEqual(clientWidth + 1)
  // ...and both numbers are still on screen, which is the point of the pairing.
  await expect(row.getByTestId("ncaaf-efficiency-off-ppa-adjusted")).toBeVisible()
  await expect(row.getByTestId("ncaaf-efficiency-off-ppa-raw")).toBeVisible()
})

test("a schedule row keeps its result and its opponent readable on a phone", async ({ page }) => {
  await mockApi(page, { ncaafTeam: "populated" })
  await mockTeamLogos(page)
  await page.goto(PATH)
  const played = TEAM_POPULATED.schedule.games.find((g: any) => g.result !== null)
  const row = page.locator(`[data-testid="ncaaf-schedule-row"][data-game-id="${played.game_id}"]`)
  await expect(row).toBeVisible()
  await expect(row.getByTestId("ncaaf-schedule-opponent")).toBeVisible()
  await expect(row.getByTestId("ncaaf-schedule-score")).toBeVisible()
  const { scrollWidth, clientWidth } = await row.evaluate((el) => ({
    scrollWidth: el.scrollWidth,
    clientWidth: el.clientWidth,
  }))
  expect(scrollWidth, "a schedule row overflows its own box").toBeLessThanOrEqual(clientWidth + 1)
})

test("the strength curve renders at a readable height on a phone", async ({ page }) => {
  // An SVG that collapses to zero height is a section that looks deliberately empty rather than
  // broken — the failure mode a desktop assertion cannot see.
  await mockApi(page, { ncaafTeam: "populated" })
  await page.goto(PATH)
  const svg = page.getByTestId("ncaaf-strength-curve").locator("svg").first()
  const box = (await svg.boundingBox())!
  expect(box.height, `the curve is ${box.height}px tall`).toBeGreaterThan(40)
  expect(box.width).toBeGreaterThan(100)
})
