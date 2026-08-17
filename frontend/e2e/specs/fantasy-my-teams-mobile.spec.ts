import { expect, test } from "@playwright/test"
import { E2E_LINKED_LEAGUES, collectPageErrors, mockApi } from "../support/api-mock"
import { signIn } from "../support/session"
import { expectNoNaN, expectNoPageErrors } from "../support/assertions"

/**
 * NF-C6b — MY TEAMS ON A PHONE.
 *
 * ══ WHY THIS FILE EXISTS ═══════════════════════════════════════════════════════════════════════
 *
 * The operator opened the shipped page on a phone and had to scroll left-and-right to read the
 * numbers. Nothing caught it: `fantasy-my-teams.spec.ts` runs desktop-only, and at 1280px every
 * column fits, so the whole rollup could be verified as CORRECT while being unusable on the device
 * a "glance at my teams" is most likely to happen on.
 *
 * The cause was two fixed minimum widths — the roster tables at `min-w-[480px]` (pre-existing) and
 * the summary at `min-w-[520px]` (NF-C6b's own). A table wider than the viewport inside an
 * `overflow-x-auto` scrolls its own container, and once the content is wide enough the document
 * itself overflows too.
 *
 * ⭐ SCOPED TO WHAT ONLY A SMALL VIEWPORT CAN TELL YOU, following `home-mobile.spec.ts`: the
 * correctness of the rollup is asserted once, on desktop, in `fantasy-my-teams.spec.ts`. Running
 * that whole suite on both viewports would cost time and prove nothing. This file asks only whether
 * the page is READABLE on a phone.
 */

async function openMyTeamsOnAPhone(page: Parameters<typeof mockApi>[0]) {
  const errors = collectPageErrors(page)
  await signIn(page, { groups: ["subscriber"] })
  await mockApi(page, { entitlement: "entitled", leagues: "linked" })
  await page.goto("/fantasy/my-teams")
  await expect(page.getByRole("heading", { name: "My Teams" })).toBeVisible()
  return errors
}

test("My Teams never scrolls sideways on a phone", async ({ page }) => {
  const errors = await openMyTeamsOnAPhone(page)
  await expect(page.getByTestId("portfolio-summary")).toBeVisible()

  // ⭐ THE ONE THAT CATCHES A FIXED-WIDTH TABLE. A table that will not shrink widens the document
  // past the viewport and the whole page then scrolls horizontally. 1px for sub-pixel rounding.
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow, "the page scrolls horizontally on a phone").toBeLessThanOrEqual(1)

  await expectNoNaN(page)
  expectNoPageErrors(errors)
})

test("the numbers that matter are on screen without scrolling a table sideways", async ({
  page,
}) => {
  // ⚠️ THE PAGE NOT OVERFLOWING IS NOT ENOUGH. `overflow-x-auto` keeps the DOCUMENT tidy while the
  // table scrolls INSIDE its own container — which is exactly the state the operator reported, and
  // it passes the check above. So this asserts the container is not internally scrollable either,
  // and that the figures actually sit within the visible viewport.
  const errors = await openMyTeamsOnAPhone(page)

  const viewport = page.viewportSize()
  expect(viewport, "this spec is meaningless without a viewport").not.toBeNull()

  for (const testId of ["portfolio-summary", "starters-table"]) {
    const scroller = page.getByTestId(testId).locator("div.overflow-x-auto").first()
    const count = await scroller.count()
    if (count === 0) continue
    const overflow = await scroller.evaluate((el) => el.scrollWidth - el.clientWidth)
    expect(
      overflow,
      `"${testId}" scrolls sideways inside its own container on a phone, so the reader has to ` +
        `drag the table to read its numbers`,
    ).toBeLessThanOrEqual(1)
  }

  // The three figures the surface exists for must be READABLE, not merely present in the DOM.
  const card = page.locator("section").filter({ hasText: E2E_LINKED_LEAGUES.half.name }).first()
  for (const testId of ["team-best-value", "team-as-set-value", "team-gap"]) {
    const el = card.getByTestId(testId)
    await expect(el, `${testId} is not visible on a phone`).toBeVisible()
    const box = await el.boundingBox()
    expect(box, `${testId} has no layout box`).not.toBeNull()
    expect(
      box!.x + box!.width,
      `${testId} extends past the right edge of a phone screen`,
    ).toBeLessThanOrEqual(viewport!.width + 1)
  }

  // The ranked column and the bench gap are the two the summary is FOR — they must survive the
  // column drop that makes the table fit, or the table fits by hiding the point of the table.
  const firstRow = page.getByTestId("portfolio-summary").getByTestId("portfolio-row").first()
  await expect(firstRow.getByTestId("portfolio-best")).toBeVisible()
  await expect(firstRow.getByTestId("portfolio-gap")).toBeVisible()

  expectNoPageErrors(errors)
})
