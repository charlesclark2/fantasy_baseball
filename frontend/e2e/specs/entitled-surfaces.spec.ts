import { expect, test, type Page } from "@playwright/test"
import { FIXTURES, collectPageErrors, mockApi } from "../support/api-mock"
import {
  LOCK_CHIP,
  expectApiFullyMocked,
  expectNoNaN,
  expectNoPageErrors,
} from "../support/assertions"

/**
 * E9.63 — the OTHER half of the E9.56b split: an UNLOCKED payload must render REAL NUMBERS.
 *
 * ⚠️ WHAT THIS FILE DOES AND DOES NOT PROVE. The public/paid decision is made SERVER-SIDE, per
 * point, by `_may_see_values` — and that decision is not under test here (see `e2e/README.md`,
 * "The boundary"). What is under test is the render contract on either side of it: given a locked
 * payload the page must show chips and a CTA; given an unlocked one it must show numbers and NO
 * chips. Both halves are needed — a page that renders chips unconditionally would pass the locked
 * file next door and still be broken for every paying subscriber.
 *
 * The two surfaces here carry that load differently, deliberately:
 *
 *   · TRACK RECORD is a verbatim prod capture of REAL, UNLOCKED model output — public by design
 *     (`fantasy_public.py`), so a genuine payload is obtainable. This is the honest one.
 *   · PROJECTIONS-ENTITLED is generated from the real locked capture, filling exactly the fields
 *     the server's own `lockedFields` declares it stripped. Envelope, roster and FIELD SET are
 *     real; the numeric values are synthetic. There is no public unlocked form of the current
 *     season to capture, and committing the paid board to the repo is the wrong trade — the full
 *     reasoning is in `e2e/fixtures/build-entitled-fixture.mjs`.
 */

/** Table cells holding a plain number — what "real numbers rendered" actually looks like. */
async function numericCellCount(page: Page): Promise<number> {
  return page
    .locator("table tbody td")
    .evaluateAll(
      (els) => els.filter((e) => /^-?\d[\d,]*(\.\d+)?$/.test((e.textContent ?? "").trim())).length,
    )
}

test.describe("entitled Projections", () => {
  test("renders real numbers and not one lock chip", async ({ page }) => {
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, { entitlement: "entitled" })

    await page.goto("/fantasy/projections")
    await expect(page.locator("table tbody tr").first()).toBeVisible()

    expect(await page.locator(LOCK_CHIP).count(), "an entitled payload rendered a padlock").toBe(0)
    expect(
      await numericCellCount(page),
      "entitled board rendered no numeric cells",
    ).toBeGreaterThan(100)

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("the page-level upgrade ask is absent for an entitled payload", async ({ page }) => {
    await mockApi(page, { entitlement: "entitled" })
    await page.goto("/fantasy/projections")
    await expect(page.locator("table tbody tr").first()).toBeVisible()

    // Asking a subscriber to subscribe is the mirror-image defect of showing a free visitor a
    // blank page, and it is just as invisible to the toolchain.
    await expect(page.getByRole("link", { name: "Subscribe to unlock" })).toHaveCount(0)
  })

  test("the entitled and locked renders are genuinely different", async ({ page }) => {
    // Guards the suite against itself: if both fixtures rendered identically, every assertion in
    // this file and in locked-surfaces.spec.ts would be satisfied by a page that ignores
    // entitlement entirely.
    await mockApi(page, { entitlement: "locked" })
    await page.goto("/fantasy/projections")
    await expect(page.locator("table tbody tr").first()).toBeVisible()
    const lockedNumeric = await numericCellCount(page)
    const lockedChips = await page.locator(LOCK_CHIP).count()

    await page.unrouteAll({ behavior: "ignoreErrors" })
    await mockApi(page, { entitlement: "entitled" })
    await page.goto("/fantasy/projections")
    await expect(page.locator("table tbody tr").first()).toBeVisible()
    const entitledNumeric = await numericCellCount(page)
    const entitledChips = await page.locator(LOCK_CHIP).count()

    expect(entitledChips).toBe(0)
    expect(lockedChips).toBeGreaterThan(10)
    expect(entitledNumeric).toBeGreaterThan(lockedNumeric)
  })
})

test("the entitled fixture is still derived from the current locked capture", () => {
  /**
   * The one drift vector the generated fixture introduces. `npm run e2e:capture` runs the capture
   * and the builder together, so the normal path cannot drift — but a hand-run
   * `capture-fixtures.mjs` would leave the entitled fixture describing a PREVIOUS export's roster
   * while every other fixture moved on, and the split assertions above would then be comparing two
   * different boards. Cheap to state, and it fails loudly instead of quietly comparing apples to
   * a stale orange.
   */
  const locked = FIXTURES.projectionsLocked()
  const entitled = FIXTURES.projectionsEntitled()

  expect(entitled.generated_at, "re-run `npm run e2e:capture` — the fixtures are out of step").toBe(
    locked.generated_at,
  )
  expect(entitled.players.length).toBe(locked.players.length)
  expect(entitled.players[0].id).toBe(locked.players[0].id)
  // The whole point of the generator: an entitled row carries no lock marker at all.
  expect(entitled.players.every((p: any) => p.locked === undefined)).toBe(true)
})

test.describe("public Track Record (real, unlocked prod payload)", () => {
  test("renders real graded numbers with no NaN", async ({ page }) => {
    const errors = collectPageErrors(page)
    const mock = await mockApi(page)

    await page.goto("/fantasy/track-record")
    await expect(page.getByRole("heading", { name: "Track Record" })).toBeVisible()
    await expect(page.locator("table tbody tr").first()).toBeVisible()

    expect(await page.locator("table tbody tr").count()).toBeGreaterThan(10)
    expect(await numericCellCount(page)).toBeGreaterThan(50)

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("the receipts headline the locked banner quotes is actually rendered", async ({ page }) => {
    // The locked surfaces lead with this line (E9.56c: "lead with the receipts, not the ask"), so
    // a track record that fails to render leaves the conversion pitch making a claim with nothing
    // behind it on the page it points to.
    const mock = await mockApi(page)
    await page.goto("/fantasy/track-record")
    await expect(page.getByText("THE HONEST READ")).toBeVisible()
    expectApiFullyMocked(mock)
  })
})
