import { expect, test } from "@playwright/test"
import { collectPageErrors, FIXTURES, mockApi } from "../support/api-mock"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"

/**
 * E9.59 — a logged-out stranger must see the PRICE, and it must be the SERVER'S price.
 *
 * ══ WHAT THIS IS WRITTEN FROM ═══════════════════════════════════════════════════════════
 *
 * `/subscribe` is where every padlock in the product sends a free visitor, and until E9.59
 * it could not show them what it cost: the only pricing read required auth, so a logged-out
 * fetch 401'd and the page asked a stranger to create an account before naming a price.
 *
 * E9.59's decision is that the number on screen is READ FROM THE STRIPE PRICE that Checkout
 * charges against — one control plane, so display and charge cannot drift and a price change
 * is one dashboard edit with no redeploy. That decision has a specific failure mode, and it
 * is the one this file is built around:
 *
 *   ⭐ A HARDCODED PRICE LOOKS IDENTICAL TO A CORRECT ONE. `$10` rendered from a constant in
 *     the JSX passes every "the page shows a price" assertion ever written, passes `tsc`,
 *     passes `next build`, and is wrong the instant the operator edits Stripe. So the
 *     headline test does not check that A price renders — it changes the server's number and
 *     demands the DOM follow. A page that ignores the payload fails it; nothing else can.
 *
 * The second leg is the E9.56c lesson applied to this surface: a price with a dead CTA next
 * to it converts nobody. `route-integrity.spec.ts` crawls the whole funnel; this file pins
 * the pricing page's own primary CTA, because that is the one link whose death this story
 * would be directly responsible for.
 *
 * ⛔ NOT MOCKED / NOT PROVEN HERE: Stripe itself. The payload is served from a fixture, so a
 * green run says "given the API returned X, the page renders X" — it does NOT say the API
 * read the right Stripe Price, and it cannot see the API-Gateway authorizer that must be set
 * to NONE for this route to answer a logged-out browser at all. Both stay operator checks
 * (an incognito load against prod); see e2e/README.md → "The boundary".
 */

const PRICING = FIXTURES.publicPricing() as {
  unit_amount: number
  currency: string
  interval: string
  founding_slots_remaining: number
  tier: string
}

/** The fixture's $12.34 — deliberately not the real $10/$20, so a hardcoded price fails. */
const FIXTURE_PRICE = "$12.34"

test("a logged-out visitor sees the price on /subscribe", async ({ page }) => {
  const errors = collectPageErrors(page)
  const mock = await mockApi(page)

  await page.goto("/subscribe")
  await page.waitForLoadState("networkidle")

  await expect(page.getByText(FIXTURE_PRICE, { exact: false })).toBeVisible()
  // The billing period has to be beside it or the number means nothing — "$12.34" alone
  // could be a one-off, a week or a year.
  await expect(page.getByText(new RegExp(`/\\s*${PRICING.interval}`, "i")).first()).toBeVisible()

  expect(
    mock.requested.some((p) => p.startsWith("/subscription/public-pricing")),
    "the page never asked for the public price — it is rendering something else",
  ).toBe(true)
  expectApiFullyMocked(mock)
  await expectNoNaN(page)
  expectNoPageErrors(errors)
})

test("⭐ the rendered price FOLLOWS the server, so it cannot be hardcoded", async ({ page }) => {
  // The load-bearing test in this file. Serve a different amount and currency than the
  // fixture and require the DOM to change with it. A component that formats a constant
  // renders $12.34 (or $10) here and fails — which is the only way to tell "shows a price"
  // from "shows THE price", and the entire premise of sourcing it from Stripe.
  const errors = collectPageErrors(page)
  const mock = await mockApi(page, {
    transform: (pathname, body) =>
      pathname === "/subscription/public-pricing"
        ? { ...body, unit_amount: 4700, currency: "eur", founding_slots_remaining: 3 }
        : body,
  })

  await page.goto("/subscribe")
  await page.waitForLoadState("networkidle")

  const text = await page.evaluate(() => document.body.innerText)
  expect(text, "the page did not render the server's amount").toMatch(/47([.,]00)?/)
  // Currency is read from the Price too — a hardcoded "$" mislabels a non-USD amount, which
  // is a worse defect than a wrong number because it looks authoritative.
  expect(text, "the page rendered a $ for a EUR price — the currency is hardcoded").toMatch(/€|EUR/)
  expect(text, "the page still shows the un-transformed fixture price").not.toContain(FIXTURE_PRICE)
  // The scarcity count is server data on the same payload; pin it so it cannot drift into
  // decoration.
  expect(text, "the founding-seat count did not follow the server").toContain("3 founding")

  expectApiFullyMocked(mock)
  expectNoPageErrors(errors)
})

test("the price is absent, not fatal, when the pricing read fails", async ({ page }) => {
  // ⚠️ THE DEPLOY-SKEW CASE, and it is a real state this story ships INTO, not a hypothetical:
  // the API-Gateway `--authorization-type NONE` route is an operator step that lands AFTER the
  // Lambda deploy, so between the two a logged-out fetch of this endpoint 401s. Stripe being
  // unreachable with nothing cached produces the same shape (503). Either way the sign-up path
  // must survive: a pricing outage may cost the price, never the funnel.
  const errors = collectPageErrors(page)
  await mockApi(page)
  await page.route("**/__e2e-api/subscription/public-pricing*", (route) =>
    route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Unauthorized" }) }),
  )

  await page.goto("/subscribe")
  await page.waitForLoadState("networkidle")

  // The page still does its job: it explains the product and offers a way in.
  await expect(page.getByRole("heading", { name: /what a membership includes/i })).toBeVisible()
  const cta = page.getByRole("button", { name: "Continue with Google" })
  await expect(cta).toBeVisible()
  await expect(cta).toBeEnabled()
  await expectNoNaN(page)
  expectNoPageErrors(errors)
})

test("the pricing page's primary CTA resolves", async ({ page }) => {
  // E9.56c shipped a CTA pointing at a route that never existed and killed the buy path. The
  // crawl in route-integrity.spec.ts covers the funnel; this pins THIS page's own CTA, since
  // a price beside a dead link is the failure this story would own.
  await mockApi(page)
  await page.goto("/subscribe")
  await page.waitForLoadState("networkidle")

  const signIn = page.getByRole("link", { name: /already have an account/i })
  await expect(signIn).toBeVisible()
  const href = await signIn.getAttribute("href")
  expect(href, "the sign-in CTA has no href").toBeTruthy()
  const res = await page.request.get(href!)
  expect(res.status(), `the pricing page's CTA (${href}) does not resolve`).toBeLessThan(400)
})

test("the public pricing payload never carries the internal conversion count", async () => {
  // A contract assertion, not a render one. `founding_slots_used` / `founding_cap` are ours
  // and internal; shipping the CAP beside `remaining` would leak `used` as a subtraction.
  // Pinned on the FIXTURE (which the Python gate holds equal to the Pydantic model) so a
  // backend that starts sending them fails here as well as there.
  const keys = Object.keys(FIXTURES.publicPricing())
  expect(keys).not.toContain("founding_slots_used")
  expect(keys).not.toContain("founding_cap")
  expect(keys).toContain("founding_slots_remaining")
  expect(PRICING.tier).toBeTruthy()
})
