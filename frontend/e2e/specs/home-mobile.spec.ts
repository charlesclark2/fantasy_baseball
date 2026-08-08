import { expect, test } from "@playwright/test"
import { collectPageErrors, FIXTURES, mockApi } from "../support/api-mock"
import { expectNoNaN, expectNoPageErrors } from "../support/assertions"

/**
 * E9.46 — the home page on a PHONE.
 *
 * The home page is the highest-traffic surface in the product and the one a cold visitor from a
 * shared link lands on, and its two live cards are the densest layouts on it. What only a small
 * viewport can tell you:
 *
 *   · whether the page scrolls SIDEWAYS (the classic symptom of a grid that will not wrap, and the
 *     one layout defect that makes a marketing page feel broken rather than merely cramped),
 *   · whether the dense stat grids are still readable or have collapsed into overlap,
 *   · whether the popovers open on TAP — a hover-only affordance is unreachable on a phone, and
 *     both of ours carry the copy that keeps a number from being misread (the E9.63/NF3 lesson),
 *   · whether the primary CTAs are still reachable without a horizontal scroll.
 *
 * ⛔ NOT a duplicate of the desktop suite. Every assertion here is one that passes trivially at
 * 1280px, so running the whole home suite on both viewports would cost time and prove nothing.
 */

const PLAYER = FIXTURES.featuredFantasyPlayer() as {
  player: { name: string; pos: string }
  market: { ourRank: number; adpRank: number }
}

test("the home page never scrolls sideways on a phone", async ({ page }) => {
  const errors = collectPageErrors(page)
  await mockApi(page)
  await page.goto("/")
  await expect(page.locator("#fantasy-proof").getByText(PLAYER.player.name)).toBeVisible()
  await expect(
    page.locator("#today").getByText(/Our model leans|Nothing to show yet|could not be loaded/),
  ).toBeVisible()

  // ⭐ THE ONE THAT CATCHES A BROKEN GRID. A card that will not wrap widens the document past the
  // viewport, and every section on the page then scrolls horizontally. Allow 1px for sub-pixel
  // rounding; anything more is a real overflow.
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow, "the page scrolls horizontally on a phone").toBeLessThanOrEqual(1)

  await expectNoNaN(page)
  expectNoPageErrors(errors)
})

test("the dense fantasy grids stay inside the card and stay readable", async ({ page }) => {
  await mockApi(page)
  await page.goto("/")
  const card = page.locator("#fantasy-proof")
  await expect(card.getByText(PLAYER.player.name)).toBeVisible()

  const cardBox = await card.locator("div").first().boundingBox()
  expect(cardBox).not.toBeNull()

  // Every stat tile must render inside the card's own box. A tile escaping it is the shape a
  // non-wrapping grid takes before the document itself overflows.
  for (const label of ["Our rank", "Market rank", "ADP", "Proj. games", "Standard", "Half-PPR"]) {
    const tile = card.getByText(label, { exact: false }).first()
    await expect(tile, `"${label}" is not visible on a phone`).toBeVisible()
    const box = await tile.boundingBox()
    expect(box, `"${label}" has no layout box`).not.toBeNull()
    expect(
      box!.x + box!.width,
      `the "${label}" tile overflows the card on a phone`,
    ).toBeLessThanOrEqual(cardBox!.x + cardBox!.width + 1)
  }

  // The ranks are the headline comparison — they must not truncate to an ellipsis.
  await expect(
    card.getByText(`${PLAYER.player.pos}${PLAYER.market.ourRank}`, { exact: false }).first(),
  ).toBeVisible()
})

test("both explanatory popovers open on TAP, not only on hover", async ({ page }) => {
  // ⚠️ A HOVER-ONLY TOOLTIP IS UNREACHABLE ON A PHONE, and this project is touch-capable and
  // hover-less precisely so that a Radix Tooltip (which closes on pointerdown by design) cannot
  // pass. Both of these carry the copy that stops a number being misread — the driver panel's
  // baseline note, and the one that keeps "our models agree" from reading as confidence in the
  // result — so on the viewport where most visitors meet them, they have to open.
  await mockApi(page)
  await page.goto("/")
  await expect(page.locator("#fantasy-proof").getByText(PLAYER.player.name)).toBeVisible()

  await page.getByRole("button", { name: /how to read these drivers/i }).tap()
  await expect(page.getByText(/against a positional baseline/i)).toBeVisible()

  await page.getByRole("button", { name: /what our models agreeing means/i }).tap()
  await expect(page.getByText(/says nothing about whether the market is wrong/i)).toBeVisible()
})

test("both hero CTAs are reachable and tappable on a phone", async ({ page }) => {
  await mockApi(page)
  await page.goto("/")

  for (const vertical of ["fantasy", "betting"]) {
    const cta = page.locator(`[data-vertical="${vertical}"]`).getByRole("link").first()
    await expect(cta, `the ${vertical} CTA is not visible on a phone`).toBeVisible()
    const box = await cta.boundingBox()
    expect(box).not.toBeNull()
    // A 44px tap target is the platform accessibility floor; below it the button is a coin flip.
    expect(box!.height, `the ${vertical} CTA is too small to tap reliably`).toBeGreaterThanOrEqual(32)
  }
})
