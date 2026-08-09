import { expect, test } from "@playwright/test"
import { collectPageErrors, mockApi } from "../support/api-mock"
import { expectNoPageErrors } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"

/**
 * E9.60 — About, FAQ and the signed-out nav must tell the SAME story as the home page.
 *
 * ══ WHY A RENDERED CHECK, WHEN THE COPY MODULE IS ALREADY SCREENED ═════════════════════════════
 *
 * `betting_ml/tests/test_e9_60_positioning_copy.py` screens `lib/positioning-copy.ts`. It cannot
 * see three things, and all three are how this defect shipped in the first place:
 *
 *   1. ⭐ A STRING THAT IS NEVER RENDERED. The copy module is only a fix if the pages read it —
 *      the "wired but never invoked" class (NF-C0e (b)). A source scan of the module passes
 *      whether or not a single component imports it.
 *   2. ⭐ EVERY STATIC STRING A COMPONENT CONTRIBUTES. Headings, CTA labels, nav item text and the
 *      accordion triggers never pass through the copy module, so no export-side denylist has ever
 *      read them — and they are exactly where a well-meaning copy edit puts a claim.
 *   3. ⭐ WHETHER THE NAV ACTUALLY OFFERS BOTH PRODUCTS TO A LOGGED-OUT VISITOR. That is a
 *      rendering question about auth state and viewport, invisible to `tsc` and to `next build`.
 *
 * ⚠️ THE DEFECT THIS STORY FIXED WAS EXACTLY A "GREEN BUILD, WRONG PAGE" — About and FAQ were
 * type-correct, fully rendering, and describing a company that no longer existed. Nothing except a
 * check on the rendered document can catch that class.
 *
 * ⚠️ SIGNED OUT THROUGHOUT. `mockApi` provides no token, which is the state these surfaces are
 * written for — a first-touch visitor. The signed-in nav is a different menu and is not this
 * story's subject.
 */

/** The positioning contract, in one place: these are the claims the whole site must agree on. */
const LIVE_NOW = ["draft rankings", "player projections"]
/** ⛔ NOT SHIPPED (spec §3.2). Present on About, but only ever as "coming this season". */
const NOT_SHIPPED = ["weekly projections", "start/sit", "waiver", "matchup-aware"]

async function bodyText(page: import("@playwright/test").Page): Promise<string> {
  return (await page.locator("body").innerText()).toLowerCase()
}

// ══════════════════════════════════════════════════════════════════════════════════════════════
// AC 1 — the pages render at all, and make no forbidden claim
// ══════════════════════════════════════════════════════════════════════════════════════════════
for (const route of ["/about", "/faq"]) {
  test(`${route} renders with no console error and no forbidden claim`, async ({ page }) => {
    const errors = collectPageErrors(page)
    await mockApi(page)
    const res = await page.goto(route)
    expect(res?.status(), `${route} did not load`).toBeLessThan(400)

    const text = await bodyText(page)
    // ⚠️ A VACUITY FLOOR. A page that rendered an empty shell would pass every "does not contain"
    // clause below, and that is the failure mode of a static page whose data module went missing.
    expect(text.length, `${route} rendered almost no text — the clauses below would be vacuous`)
      .toBeGreaterThan(1500)

    // ⭐ THE RENDERED SCAN. Catches headings and CTA labels the Python screening structurally
    // cannot see, because they never enter the copy module.
    expect(forbiddenPhrasesIn(text), `${route} renders a forbidden claim`).toEqual([])
    expectNoPageErrors(errors)
  })
}

// ══════════════════════════════════════════════════════════════════════════════════════════════
// AC 2 — About tells the two-product story, fantasy first
// ══════════════════════════════════════════════════════════════════════════════════════════════
test("About leads with the company positioning, not a baseball-only one", async ({ page }) => {
  await mockApi(page)
  await page.goto("/about")

  await expect(
    page.getByRole("heading", { level: 1, name: /knowing what you don't know/i }),
  ).toBeVisible()

  const text = await bodyText(page)
  // The retired one-product identity, asserted as an ABSENCE so it cannot creep back.
  expect(text, "About still describes a baseball-only company").not.toContain("forecast baseball")
  expect(text).toContain("fantasy")
  expect(text).toContain("mlb")
})

test("About shows both products, with fantasy first", async ({ page }) => {
  await mockApi(page)
  await page.goto("/about")

  // ⚠️ LOCATED BY `data-product`, NOT BY TEXT. Both product names appear elsewhere on the page
  // (the CTA row, the beliefs), so a text locator would be satisfied with the whole section
  // deleted — the collision class `home-positioning.spec.ts` records for the fantasy door.
  const products = page.locator("[data-product]")
  await expect(products).toHaveCount(2)
  await expect(page.locator('[data-product="fantasy"]')).toBeVisible()
  await expect(page.locator('[data-product="betting"]')).toBeVisible()

  // Fantasy first — the same order as the home page's VERTICALS and the nav.
  expect(await products.first().getAttribute("data-product")).toBe("fantasy")
})

test("an unshipped capability is never presented as available", async ({ page }) => {
  await mockApi(page)
  await page.goto("/about")

  // ⭐⭐ THE CLAUSE THIS WHOLE STORY EXISTS FOR, and the reason the live/coming split is DATA.
  // Both lists render the same words in different boxes, so only a structural read can tell
  // "weekly projections are coming" from "weekly projections are available".
  const live = (await page.locator('[data-capability="live"]').allInnerTexts()).join(" ").toLowerCase()
  const coming = (await page.locator('[data-capability="coming"]').allInnerTexts()).join(" ").toLowerCase()

  expect(live.length, "no live capability block rendered — this clause would be vacuous")
    .toBeGreaterThan(50)
  expect(coming.length, "no coming block rendered — this clause would be vacuous").toBeGreaterThan(50)

  for (const shipped of LIVE_NOW) {
    expect(live, `${shipped} is shipped but is not listed as available`).toContain(shipped)
  }
  for (const unshipped of NOT_SHIPPED) {
    expect(live, `${unshipped} has NOT shipped but is listed as available now`).not.toContain(unshipped)
    // ⭐ The other half: deleting it entirely would satisfy the clause above and hide the roadmap.
    expect(coming, `${unshipped} vanished rather than being labelled coming`).toContain(unshipped)
  }

  // ⛔ A not-yet-live capability is TEXT, never a link (E9.56c's dead `/pricing` class).
  await expect(page.locator('[data-capability="coming"] a')).toHaveCount(0)
})

test("About links to the evidence rather than quoting its number", async ({ page }) => {
  await mockApi(page)
  await page.goto("/about")
  // NF-TR1's rule for a marketing surface. The fantasy record is the one genuinely open to an
  // anonymous visitor, which is why it is the one linked.
  await expect(page.locator('a[href="/fantasy/track-record"]').first()).toBeVisible()
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// AC 3 — the FAQ covers both products and no longer sizes bets
// ══════════════════════════════════════════════════════════════════════════════════════════════
test("the FAQ has a section per product, in the site's order", async ({ page }) => {
  await mockApi(page)
  await page.goto("/faq")

  const sections = page.locator("[data-faq-section]")
  await expect(sections).not.toHaveCount(0)
  const names = (await sections.evaluateAll((els) =>
    els.map((e) => e.getAttribute("data-faq-section") ?? ""),
  )).map((s) => s.toLowerCase())

  const fantasy = names.findIndex((n) => n.includes("fantasy"))
  const betting = names.findIndex((n) => n.includes("betting"))
  expect(fantasy, "the FAQ has no fantasy section").toBeGreaterThanOrEqual(0)
  expect(betting, "the FAQ has no betting section").toBeGreaterThanOrEqual(0)
  expect(fantasy, "the FAQ puts betting before fantasy").toBeLessThan(betting)
})

test("the FAQ no longer says Credence is an MLB-only company", async ({ page }) => {
  await mockApi(page)
  await page.goto("/faq")
  const text = await bodyText(page)
  expect(text, "the retired MLB-only framing is still on the FAQ").not.toContain("mlb baseball only")
  expect(text).not.toContain("baseball analytics tool")
})

test("the FAQ carries no stake-sizing guidance", async ({ page }) => {
  await mockApi(page)
  await page.goto("/faq")
  // ⚠️ THE ACCORDION TRIGGERS RENDER THE QUESTIONS EVEN WHEN COLLAPSED, so a body scan sees every
  // question; Radix keeps collapsed ANSWER content out of the DOM, which is why this clause is
  // written against the questions rather than the answers.
  const text = await bodyText(page)
  expect(text, "the public FAQ still tells visitors how much to bet").not.toContain("kelly")
  expect(text).not.toContain("how much should i bet")
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// AC 4 — a signed-out visitor finds a door to BOTH products
// ══════════════════════════════════════════════════════════════════════════════════════════════
test("the signed-out desktop nav offers both products", async ({ page }) => {
  await mockApi(page)
  await page.goto("/about")

  // ⚠️ SCOPED TO THE PRIMARY <nav> AND EXCLUDING THE FOOTER — `SiteFooter` wraps its own links in a
  // `<nav>`, the collision `home-positioning.spec.ts` hit on its blog clause.
  const doors = await page.evaluate(() =>
    [...document.querySelectorAll("nav [data-signed-out-nav]")]
      .filter((el) => !el.closest("footer"))
      .map((el) => el.getAttribute("data-signed-out-nav") ?? ""),
  )

  expect(doors.length, "the signed-out nav rendered nothing — this clause would be vacuous")
    .toBeGreaterThan(0)
  expect(doors, "the signed-out nav has no door to the fantasy product").toContain("fantasy")
  expect(doors, "the signed-out nav has no door to the MLB betting product").toContain("betting")
  // Fantasy first, matching About and the home page.
  expect(doors.indexOf("fantasy")).toBeLessThan(doors.indexOf("betting"))
})

test("the signed-out MLB door does not lead to a login wall", async ({ page }) => {
  await mockApi(page)
  await page.goto("/about")

  const href = await page
    .locator('nav [data-signed-out-nav="betting"]')
    .first()
    .getAttribute("href")
  expect(href, "no MLB door found in the signed-out nav").toBeTruthy()
  // ⛔ Every MLB betting route is mounted `dependencies=_paid`; the public MLB surface is the home
  // page's featured read. A door into any of these would be a login wall wearing a product label.
  for (const gated of ["/performance", "/dashboard", "/picks", "/props", "/ev-tracker"]) {
    expect(href, `the signed-out MLB door points at the gated ${gated}`).not.toContain(gated)
  }
})

test("the FAQ is reachable from the signed-out mobile nav", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockApi(page)
  await page.goto("/about")

  // The phone menu is the viewport with room for the full set — and before E9.60 the FAQ had no
  // nav entry at ANY width.
  await page.getByRole("button", { name: /toggle menu/i }).click()

  // ⚠️ `nav a[href="/faq"]` IS NOT A VALID SCOPE, and this clause failed on it first: `SiteFooter`
  // wraps its own links in a `<nav>`, so the selector matched the FOOTER's FAQ link too and blew up
  // on strict mode. The identical collision `home-positioning.spec.ts` records for its blog clause
  // — and had the footer link been the only match, this would have passed while the nav entry was
  // missing, which is the failure that actually matters.
  // ⚠️ `:visible`, NOT `.first()`. The desktop bar renders its own copy of the betting door with
  // `hidden … sm:block`, and it comes FIRST in the DOM — so `.first()` resolved to an element that
  // is correctly hidden at 390px and the clause failed on the wrong node. The property being
  // asserted is "a door to each product is REACHABLE at this viewport", which is what `:visible`
  // actually says.
  const navFaq = page.locator('nav [data-signed-out-nav="company"][href="/faq"]:visible')
  await expect(navFaq, "the FAQ is not in the signed-out mobile nav").toBeVisible()
  await expect(
    page.locator('nav [data-signed-out-nav="betting"]:visible'),
    "the MLB door is not reachable from the signed-out mobile nav",
  ).toBeVisible()
})

test("About and FAQ reach each other, and the footer reaches both", async ({ page }) => {
  await mockApi(page)
  await page.goto("/about")
  // The About CTA row carries the FAQ; the footer (on every page) carries both.
  await expect(page.locator('a[href="/faq"]').first()).toBeVisible()
  await expect(page.locator('footer a[href="/about"]')).toBeVisible()
  await expect(page.locator('footer a[href="/faq"]')).toBeVisible()
})
