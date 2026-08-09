import { expect, test, type Page } from "@playwright/test"
import { collectPageErrors, mockApi } from "../support/api-mock"
import { expectNoPageErrors } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"
import { signIn } from "../support/signed-in"

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
 * ⚠️ BOTH AUTH STATES. The positioning and copy clauses run SIGNED OUT, which is the state those
 * surfaces are written for — a first-touch visitor. The nav clauses run in BOTH, via
 * `support/signed-in.ts`, because the two menus are rendered by two different branches and the
 * mobile bug this story fixes lives in the SIGNED-IN one: Sign Out and Settings exist nowhere else.
 * A fix verified only signed-out would have left the reported defect exactly as it was.
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
    [...document.querySelectorAll("[data-primary-nav] [data-signed-out-nav]")]
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
    .locator('[data-primary-nav] [data-signed-out-nav="betting"]')
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
  const navFaq = page.locator('[data-primary-nav] [data-signed-out-nav="company"][href="/faq"]:visible')
  await expect(navFaq, "the FAQ is not in the signed-out mobile nav").toBeVisible()
  await expect(
    page.locator('[data-primary-nav] [data-signed-out-nav="betting"]:visible'),
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

// ══════════════════════════════════════════════════════════════════════════════════════════════
// AC 5 — ⭐ THE LIVE MOBILE-NAV BUG (operator, 2026-08-09)
// ══════════════════════════════════════════════════════════════════════════════════════════════
//
// The open mobile menu had no height cap inside a `sticky top-0` nav, so on a phone it grew past
// the viewport and spilled into the page flow — putting SIGN OUT and Settings below the fold of
// whatever page you were on. Reaching Sign Out meant scrolling to the bottom of the entire page,
// and closing the menu then left the page somewhere the user never chose to be.
//
// ⚠️ WHY THESE RUN AT EXPLICIT VIEWPORTS RATHER THAN ON THE `mobile` PROJECT. The bug is a
// RELATIONSHIP between the menu's height and the viewport's, so the shortest viewport is the one
// that matters — iPhone SE (667px) is 200px shorter than a Pixel 7 and is where a menu that "fits"
// on the taller phone does not. Running both, named, is the point; inheriting one project's
// viewport would test the easier case and report the harder one as covered.
const PHONES = [
  { name: "Pixel 7", width: 412, height: 915 },
  { name: "iPhone SE", width: 375, height: 667 },
]

/** The open menu panel — the element that must own its own scroll. */
const PANEL = "[data-primary-nav] div.overflow-y-auto"

async function openMobileMenu(page: Page) {
  await page.getByRole("button", { name: /toggle menu/i }).click()
  await expect(page.locator(PANEL)).toBeVisible()
}

for (const phone of PHONES) {
  test(`${phone.name}: the signed-in mobile menu keeps Sign Out reachable without scrolling the page`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: phone.width, height: phone.height })
    await signIn(page)
    await mockApi(page)
    // `/settings` renders the full authenticated chrome — the account block with Settings and Sign
    // Out is the part of the menu the bug actually buried.
    await page.goto("/settings")
    await page.waitForLoadState("networkidle")

    const scrollY = await page.evaluate(() => window.scrollY)
    await openMobileMenu(page)

    // ⭐ 1. THE CAP. The panel must not be taller than the viewport — that is the defect itself,
    // and it is the half `overflow-y-auto` alone does not fix.
    const panel = page.locator(PANEL)
    const box = await panel.boundingBox()
    expect(box, "the open menu panel has no box").toBeTruthy()
    expect(
      box!.height,
      `the open menu is ${box!.height}px tall on a ${phone.height}px viewport — it has spilled ` +
        `into the page flow again`,
    ).toBeLessThanOrEqual(phone.height)

    // ⭐ 2. IT IS ITS OWN SCROLL CONTAINER. `scrollHeight > clientHeight` is what makes "scroll
    // within the menu" a thing that can happen at all; without the cap this is false because the
    // element simply grew to fit.
    const { scrollHeight, clientHeight } = await panel.evaluate((el) => ({
      scrollHeight: el.scrollHeight,
      clientHeight: el.clientHeight,
    }))
    expect(
      scrollHeight,
      "the menu content fits without scrolling on this viewport — the scroll assertion below " +
        "would be vacuous, so this spec is no longer testing the reported bug",
    ).toBeGreaterThan(clientHeight)

    // ⭐ 3. SIGN OUT IS REACHED BY SCROLLING INSIDE THE MENU. This is the acceptance bar verbatim.
    // ⚠️ SCOPED TO THE NAV, and this is not fussiness: `/settings` renders its OWN
    // "Sign out everywhere" button, so a page-wide `/sign out/i` matched two elements and blew up
    // on strict mode. Worse, had the nav's button been the one missing, a loose locator would have
    // found the settings button and PASSED — the exact collision class the fantasy-door and
    // market-label locators in `home-positioning.spec.ts` both record.
    const signOut = page.locator("[data-primary-nav]").getByRole("button", { name: "Sign Out", exact: true })
    await signOut.scrollIntoViewIfNeeded()
    await expect(signOut).toBeInViewport()

    // ⭐ 4. THE PAGE DID NOT MOVE. `overscroll-contain` plus the cap means the document scroll is
    // untouched — the other half of the acceptance bar, and the part that made the old behaviour
    // actively disorienting rather than merely awkward.
    expect(
      await page.evaluate(() => window.scrollY),
      "reaching Sign Out scrolled the underlying page",
    ).toBe(scrollY)
  })

  test(`${phone.name}: the signed-out mobile menu also stays inside the viewport`, async ({ page }) => {
    await page.setViewportSize({ width: phone.width, height: phone.height })
    await mockApi(page)
    await page.goto("/about")

    await openMobileMenu(page)
    const box = await page.locator(PANEL).boundingBox()
    expect(box, "the open menu panel has no box").toBeTruthy()
    // Both auth states share one class, but they are rendered by two different branches — a fix
    // applied to one is invisible in the other, which is exactly how half a fix ships.
    expect(
      box!.height,
      `the signed-out menu is ${box!.height}px tall on a ${phone.height}px viewport`,
    ).toBeLessThanOrEqual(phone.height)

    // The last item in this panel is Sign In; it must be reachable the same way.
    const signIn = page.locator('[data-primary-nav] a[href="/login"]:visible')
    await signIn.scrollIntoViewIfNeeded()
    await expect(signIn).toBeInViewport()
  })
}

// ══════════════════════════════════════════════════════════════════════════════════════════════
// AC 6 — the nav IA holds in the SIGNED-IN state too
// ══════════════════════════════════════════════════════════════════════════════════════════════
test("the signed-in nav leads with fantasy and carries Track Record top-level", async ({ page }) => {
  await signIn(page)
  await mockApi(page)
  await page.goto("/about")
  await page.waitForLoadState("networkidle")

  // ⚠️ ASSERT THE SIGNED-IN CHROME ACTUALLY RENDERED FIRST. If the seeded session did not take
  // (a client-id drift in `signed-in.ts` would do it silently), every clause below would be
  // asserting about a signed-OUT page while reading as coverage.
  const subNav = page.locator("[data-primary-nav]").getByRole("link", { name: "What's New" })
  await expect(subNav, "the signed-in sub-nav did not render — the seeded session did not take")
    .toBeVisible()

  const triggers = await page
    .locator("[data-primary-nav] button")
    .evaluateAll((els) => els.map((e) => (e.textContent ?? "").trim()))
  const nfl = triggers.findIndex((t) => t.startsWith("NFL"))
  const mlb = triggers.findIndex((t) => t.startsWith("MLB"))
  expect(nfl, "no NFL dropdown in the signed-in nav").toBeGreaterThanOrEqual(0)
  expect(mlb, "no MLB dropdown in the signed-in nav").toBeGreaterThanOrEqual(0)
  expect(nfl, "the signed-in nav leads with MLB; every other surface leads with fantasy")
    .toBeLessThan(mlb)

  await expect(
    page.locator("[data-primary-nav]").getByRole("link", { name: "Track Record", exact: true }),
    "Track Record is not a top-level entry in the signed-in nav",
  ).toBeVisible()
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// AC 7 — the footer: fantasy-first, and an un-shipped product is never a link
// ══════════════════════════════════════════════════════════════════════════════════════════════
test("the footer leads with fantasy and never links an unshipped product", async ({ page }) => {
  await mockApi(page)
  await page.goto("/about")

  const footer = page.locator("footer")
  const text = (await footer.innerText()).toLowerCase()
  expect(text.indexOf("fantasy football"), "the footer has no fantasy product entry")
    .toBeGreaterThanOrEqual(0)
  expect(
    text.indexOf("fantasy football"),
    "the footer leads with MLB; every other surface leads with fantasy",
  ).toBeLessThan(text.indexOf("mlb betting intelligence"))

  // ⛔ E9.56c's dead-`/pricing` class. The coming rows must be listed AND unclickable.
  expect(text, "the un-shipped verticals vanished rather than being labelled").toContain(
    "ncaaf betting intelligence",
  )
  expect(text).toContain("coming this season")
  const comingLinks = await footer
    .locator("a")
    .evaluateAll((els) =>
      els.filter((e) => /ncaaf|nfl betting/i.test(e.textContent ?? "")).length,
    )
  expect(comingLinks, "an un-shipped product is rendered as a link in the footer").toBe(0)
})
