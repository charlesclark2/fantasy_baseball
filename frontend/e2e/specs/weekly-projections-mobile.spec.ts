import { expect, test } from "@playwright/test"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { collectPageErrors, mockApi } from "../support/api-mock"
import { expectNoNaN, expectNoPageErrors } from "../support/assertions"

/**
 * NF-WK-FE1 — the weekly page on a phone. Registered in the `mobile` project.
 *
 * ⭐ WHY ITS OWN FILE, AND THE TWO REASONS ARE BOTH PRECEDENTED.
 *
 *  1. THE DEFINITION TAPS ARE VACUOUS ON DESKTOP. `InfoTip` opens on `pointerenter` when
 *     `pointerType === "mouse"`, so Chromium's `click()` opens it via HOVER before the click is
 *     even dispatched — a Radix Tooltip, which no touch can ever open, would pass identically.
 *     This page carries FOUR of them, and one is load-bearing in a way the others are not: the
 *     RANGE definition is where "this number is an average, most weeks land either side of it"
 *     lives. A phone reader who cannot open it meets a confident-looking point projection with its
 *     honest framing unreachable — which is the whole thing this surface exists not to do. Same
 *     argument `expected-points-label`, `availability-flag` and `stat-line-suppression` each make.
 *
 *  2. THE TABLE IS WIDER THAN A PHONE, DELIBERATELY, and that is only safe if it scrolls INSIDE
 *     its own box. ⭐ A container that scrolls leaves the DOCUMENT perfectly tidy, so a page-level
 *     check alone would pass while a reader drags the whole page sideways — NF-C6P3's lesson, and
 *     the reason the clause below asserts BOTH directions rather than one.
 */

const FIXTURE_DIR = join(process.cwd(), "e2e", "fixtures", "api")
const readFixture = (name: string) => JSON.parse(readFileSync(join(FIXTURE_DIR, name), "utf8"))
const MANIFEST = readFixture("fantasy-nfl-weekly-manifest.synthetic.json")

const PATH = "/fantasy/weekly"

test("the weekly page never scrolls sideways on a phone", async ({ page }) => {
  const errors = collectPageErrors(page)
  await mockApi(page)
  await page.goto(PATH)
  await expect(page.getByTestId("weekly-row").first()).toBeVisible()

  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  expect(scrollWidth, `the document is ${scrollWidth}px wide in a ${clientWidth}px viewport`)
    .toBeLessThanOrEqual(clientWidth + 1)

  // ⭐ AND THE OTHER DIRECTION: the TABLE is supposed to be wider than the phone. If it were not,
  // this spec would be passing because the table had silently collapsed rather than because it is
  // correctly contained — the difference between a contained overflow and no content at all.
  const table = page.locator("table").first()
  const overflows = await table.evaluate((el) => {
    const box = el.closest("[class*='overflow-x-auto']") as HTMLElement | null
    return box ? { scroll: box.scrollWidth, client: box.clientWidth } : null
  })
  expect(overflows, "the weekly table is not inside an overflow-x-auto container").not.toBeNull()
  expect(
    overflows!.scroll,
    "the table is NOT wider than its container — this clause would be passing on a collapsed table",
  ).toBeGreaterThan(overflows!.client)
})

test("the range definition opens on TAP, where its whole honest framing lives", async ({ page }) => {
  await mockApi(page)
  await page.goto(PATH)
  await expect(page.getByTestId("weekly-row").first()).toBeVisible()

  // ⚠️ `tap()`, not `click()`. A `click` on this project would still be a touch-less synthetic
  // event in some browsers; `tap` is what a phone reader actually does, and it is the one gesture
  // a Radix Tooltip could never satisfy.
  const trigger = page.getByRole("button", { name: /80% range/i }).first()
  await expect(trigger).toBeVisible()
  await trigger.tap()

  // The definition's load-bearing half: the point is an average, and weeks land either side of it.
  await expect(page.getByText(/one week in ten/i).first()).toBeVisible()
})

test("the interval notes and the absence reasons are reachable on a phone", async ({ page }) => {
  const errors = collectPageErrors(page)
  await mockApi(page)
  await page.goto(PATH)

  // ⭐ THESE ARE THE PAGE'S HONEST-FRAMING BLOCKS, and a phone layout that pushed them off-screen
  // or clipped them to zero height would remove the measurement from exactly the reader most
  // likely to act on a single number. `toBeVisible` fails on a zero-size box, which is the failure
  // mode a text-presence assertion cannot see.
  await expect(page.getByTestId("weekly-interval-note")).toBeVisible()
  await expect(page.getByTestId("weekly-ros-interval-note")).toBeVisible()

  const absences = page.getByTestId("weekly-absences")
  await absences.scrollIntoViewIfNeeded()
  await expect(absences).toBeVisible()
  for (const a of MANIFEST.absences.filter((x: { n: number }) => x.n > 0)) {
    await expect(absences.getByTestId(`weekly-absence-${a.reason}`)).toBeVisible()
  }

  expectNoPageErrors(errors)
  await expectNoNaN(page)
})

test("the awaiting-publish state is legible on a phone, and is not a spinner", async ({ page }) => {
  await mockApi(page, { weekly: "awaiting" })
  await page.goto(PATH)
  const notice = page.getByTestId("weekly-awaiting-publish")
  await expect(notice).toBeVisible()
  const box = await notice.boundingBox()
  expect(box, "the awaiting-publish notice has no box at phone width").not.toBeNull()
  expect(box!.width).toBeGreaterThan(200)
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1)
})
