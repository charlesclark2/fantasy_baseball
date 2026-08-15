import { expect, test, type Page } from "@playwright/test"
import { collectPageErrors, mockApi } from "../support/api-mock"
import { signIn } from "../support/session"
import { expectNoPageErrors } from "../support/assertions"

/**
 * E5.10 — /props slate navigation on a PHONE.
 *
 * ⛔ NOT a duplicate of `props-slate-nav.spec.ts` — every assertion here is one that passes
 * trivially on desktop (a mouse click and a tap look identical to a `<button>`) and needs a real
 * touch-capable, hover-less viewport to mean anything, the same reasoning `home-mobile.spec.ts`
 * documents. It is mobile-ONLY (see `playwright.config.ts`'s `testIgnore`/`testMatch`) because
 * `page.tap()` throws outright on `Desktop Chrome` ("The page does not support tap").
 */

const LAST_GAME_PK = 900006

async function openProps(page: Page) {
  const errors = collectPageErrors(page)
  await signIn(page, { groups: [] })
  const mock = await mockApi(page)
  await page.goto("/props")
  await expect(page.getByRole("heading", { name: "Props" })).toBeVisible()
  await page.getByRole("button", { name: "Total Bases (TB)" }).click()
  await expect(page.getByTestId("props-game-groups")).toBeVisible()
  return { errors, mock }
}

function gameGroup(page: Page, gamePk: number) {
  return page.locator(`[data-testid="props-game-group"][data-game-pk="${gamePk}"]`)
}

test("the slate never scrolls sideways on a phone", async ({ page }) => {
  const { errors } = await openProps(page)

  // ⭐ THE ONE THAT CATCHES A BROKEN GRID/FILTER ROW. A filter-chip row or a card grid that will not
  // wrap widens the document past the viewport — this is a 108-card, 6-team, multi-line-value
  // slate, the densest surface the filter chips will ever render against.
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow, "the props page scrolls horizontally on a phone").toBeLessThanOrEqual(1)
  expectNoPageErrors(errors)
})

test("a collapsed game header is tappable and expands its section", async ({ page }) => {
  await openProps(page)
  const last = gameGroup(page, LAST_GAME_PK)
  await expect(last.getByTestId("props-card")).toHaveCount(0)

  await last.getByTestId("props-game-header").tap()
  await expect(last.getByTestId("props-card").first()).toBeVisible()

  // …and tapping again collapses it — a real toggle, reachable on touch, not just on click.
  await last.getByTestId("props-game-header").tap()
  await expect(last.getByTestId("props-card")).toHaveCount(0)
})

test("a team filter chip is tappable and narrows the slate to that matchup", async ({ page }) => {
  await openProps(page)
  await page.getByTestId("props-filter-team-STL").tap()
  await expect(page.getByTestId("props-game-group")).toHaveCount(1)
  await expect(gameGroup(page, LAST_GAME_PK)).toBeVisible()
})

test("Sort is a Radix Picker, not a native <select> — driven by trigger-tap then option-tap", async ({
  page,
}) => {
  // A raw <select> trips the mobile-form-control guard AND `selectOption` silently no-ops on a
  // Radix trigger (`components/ui/picker.tsx` explains why the raw element is forbidden repo-wide;
  // NF-C6P2 documents the same lesson for `/fantasy/roster-report`'s League picker). This is the
  // props page's own proof that its sort control chose the right primitive.
  await openProps(page)
  await expect(page.locator("select#props-sort")).toHaveCount(0) // the id is on a <button>, not a <select>
  await page.getByLabel("Sort", { exact: true }).tap()
  await page.getByRole("option", { name: "Proj TB", exact: true }).tap()
  await expect(page.getByLabel("Sort", { exact: true })).toContainText("Proj TB")
})
