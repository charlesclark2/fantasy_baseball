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
// AC 4 — every signed-out nav entry opens for the visitor it is drawn for
// ══════════════════════════════════════════════════════════════════════════════════════════════
test("the signed-out desktop nav names the fantasy sport and offers no MLB door", async ({
  page,
}) => {
  await mockApi(page)
  await page.goto("/about")

  // ⚠️ SCOPED TO THE PRIMARY <nav> AND EXCLUDING THE FOOTER — `SiteFooter` wraps its own links in a
  // `<nav>`, the collision `home-positioning.spec.ts` hit on its blog clause.
  const doors = await page.evaluate(() =>
    [...document.querySelectorAll("[data-primary-nav] [data-signed-out-nav]")]
      .filter((el) => !el.closest("footer"))
      .map((el) => ({
        product: el.getAttribute("data-signed-out-nav") ?? "",
        text: (el.textContent ?? "").trim(),
      })),
  )

  expect(doors.length, "the signed-out nav rendered nothing — this clause would be vacuous")
    .toBeGreaterThan(0)
  expect(
    doors.map((d) => d.product),
    "the signed-out nav has no door to the fantasy product",
  ).toContain("fantasy")

  // ⭐ OPERATOR, 2026-08-09 — the sport is NAMED. `nav-model.ts` already declares an MLB→Fantasy
  // surface, so a bare "Fantasy" is ambiguous the moment the baseball board stops being admin-only.
  const fantasyBar = page.locator('[data-primary-nav] [data-signed-out-nav="fantasy"]:visible')
  await expect(
    fantasyBar.filter({ hasText: /fantasy football/i }).first(),
    "the fantasy door does not name its sport",
  ).toBeVisible()

  // ⛔ NO MLB DOOR — reversing E9.60's own first cut. There is no MLB destination an anonymous
  // visitor can open (every route is `dependencies=_paid`, and the product is intended to become
  // signup-gated rather than public), so the entry could only ever be an anchor into the home
  // page. Read the SIGNED_OUT_NAV section header in `positioning-copy.ts` before re-adding one.
  expect(
    doors.map((d) => d.product),
    "an MLB/betting door was re-added to the signed-out nav",
  ).not.toContain("betting")
})

test("no signed-out nav entry leads to a login wall", async ({ page }) => {
  await mockApi(page)
  await page.goto("/about")

  // ⚠️ WIDENED from the single MLB door to EVERY entry when that door was removed. The narrow
  // version located `[data-signed-out-nav="betting"]`, which no longer exists — so it would have
  // failed on its own missing fixture rather than on the property. This asks the real question,
  // and of more links than the original did.
  const hrefs = await page
    .locator("[data-primary-nav] [data-signed-out-nav]")
    .evaluateAll((els) => els.map((e) => e.getAttribute("href") ?? ""))
  expect(hrefs.length, "no signed-out nav entries found — this clause would be vacuous")
    .toBeGreaterThan(0)

  // ⛔ Every MLB betting route is mounted `dependencies=_paid`. A door into any of these would be
  // a login wall wearing a product label.
  for (const href of hrefs) {
    for (const gated of ["/performance", "/dashboard", "/picks", "/props", "/ev-tracker"]) {
      expect(href, `a signed-out nav entry points at the gated ${gated}`).not.toContain(gated)
    }
  }
})

test("the signed-out desktop bar fits at the breakpoint where it first renders", async ({
  page,
}) => {
  // ⭐ THE GUARD THAT TURNS "this looks like it fits" INTO A MEASUREMENT. These links are
  // `hidden sm:block`, so 640px is the NARROWEST width at which the full bar is on screen — i.e.
  // the worst case, and the one nobody develops at. E9.58 already recorded this bar overflowing
  // (the wordmark overlapped the first link, "Track Record" wrapped onto two lines), and every
  // label edit in `SIGNED_OUT_NAV` is a width edit — "Fantasy" → "Fantasy Football" is ~60px.
  await page.setViewportSize({ width: 640, height: 900 })
  await mockApi(page)
  await page.goto("/about")

  const nav = page.locator("[data-primary-nav]")
  await expect(nav).toBeVisible()

  // 1px of tolerance for sub-pixel rounding, matching `home-mobile.spec.ts`.
  const overflow = await nav.evaluate((el) => el.scrollWidth - el.clientWidth)
  expect(overflow, "the signed-out nav bar overflows horizontally at the sm breakpoint")
    .toBeLessThanOrEqual(1)

  // ⭐ NCAAF-P3.9 — RECORD THE HEADROOM, don't just pass/fail on it. This is a REPORT, not a new
  // requirement: the clause above is unchanged and still the gate.
  //
  // WHY IT EARNS ITS LINE. A flex row SHRINKS its items rather than overflowing, so this bar can
  // sit at 100% capacity and report `overflow = 0` — which is exactly what happened when P3.9 added
  // a fourth door: green on macOS, and 5px over on CI, whose Linux font metrics render the same
  // strings slightly wider. A binary check cannot tell "fits comfortably" from "fits by nothing",
  // and the difference between those two is whether the NEXT label edit is safe. The number is
  // annotated on every run so a session reads it before spending a CI cycle finding out.
  const headroom = await nav.evaluate((el) => {
    const bar = el.firstElementChild as HTMLElement
    const style = getComputedStyle(bar)
    const gap = parseFloat(style.columnGap || "0") || 0
    const kids = [...bar.children] as HTMLElement[]
    const content =
      kids.reduce((sum, k) => sum + k.getBoundingClientRect().width, 0) +
      gap * Math.max(0, kids.length - 1) +
      parseFloat(style.paddingLeft || "0") +
      parseFloat(style.paddingRight || "0")
    return Math.round(bar.clientWidth - content)
  })
  test.info().annotations.push({
    type: "signed-out-bar-headroom",
    description: `${headroom}px spare at 640px (negative means the flex row is shrinking to fit)`,
  })

  // ⚠️ AND THE LINKS MUST NOT HAVE WRAPPED. A bar can fit its container by letting a link break
  // onto a second line, which is the E9.58 symptom and is invisible to a scrollWidth check. Every
  // link carries `whitespace-nowrap`, so a wrapped link shows up as a taller-than-one-line box.
  const tall = await page
    .locator('[data-primary-nav] [data-signed-out-nav]:visible')
    .evaluateAll((els) =>
      els
        .filter((e) => e.getBoundingClientRect().height > 28)
        .map((e) => (e.textContent ?? "").trim()),
    )
  expect(tall, "a signed-out nav link wrapped onto a second line at the sm breakpoint").toEqual([])
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

  // ⚠️ THE MLB HALF OF THIS CLAUSE WAS REMOVED, not weakened, when the MLB door was (operator,
  // 2026-08-09). What is left still carries the property the clause exists for — that the phone
  // menu renders the FULL `SIGNED_OUT_NAV` set rather than the `desktop` subset — because FAQ is
  // itself a `desktop: false` entry and appears at no other viewport.
  await expect(
    page.locator('[data-primary-nav] [data-signed-out-nav="fantasy"]:visible').first(),
    "the fantasy doors are not reachable from the signed-out mobile nav",
  ).toBeVisible()
})

test("the About CTA is two tiers, not one row that orphans a button", async ({ page }) => {
  // ⭐ THE REPORTED DEFECT (operator screenshot, 2026-08-09): five equal-weight buttons in a
  // `flex-wrap` broke 4 + 1 at desktop width — a lone orphan under a full row.
  //
  // ⚠️ ASSERTED AS "HOW MANY ROWS DO THESE OCCUPY", by their y-positions, because that is the
  // actual complaint. A count-of-buttons check would pass on any layout, and a width check cannot
  // tell a deliberate second tier from an accidental wrap.
  await page.setViewportSize({ width: 1280, height: 900 })
  await mockApi(page)
  await page.goto("/about")

  const cta = page.locator("main div").filter({ hasText: /Questions about how Credence works/ }).last()
  const buttons = cta.locator("a.rounded-md")
  const count = await buttons.count()
  expect(count, "no CTA buttons found — this clause would be vacuous").toBeGreaterThan(0)

  // Group by top edge; each distinct top is a rendered row.
  const tops = await buttons.evaluateAll((els) =>
    [...new Set(els.map((e) => Math.round(e.getBoundingClientRect().top)))],
  )
  expect(tops.length, "the CTA buttons wrap onto more than one row").toBe(1)
  expect(count, "the button tier grew back past what fits on one row").toBeLessThanOrEqual(3)
})

test("the FAQ does not reprint the site footer above the site footer", async ({ page }) => {
  await mockApi(page)
  await page.goto("/faq")

  // ⭐ The removed row was About · Track Record · Contact · Privacy Policy · Terms of Service —
  // every one of them already in `SiteFooter`, rendered directly beneath. Asserted as "these
  // destinations appear exactly once outside the footer", which is the duplication itself rather
  // than the particular markup that caused it.
  // ⚠️ THE NAV IS EXCLUDED AS WELL AS THE FOOTER, and this clause failed on it first: About is a
  // legitimate `SIGNED_OUT_NAV` entry, so it appears in the top bar on every page and the top bar
  // is not inside `<footer>`. The property is about the PAGE BODY reprinting site chrome, so both
  // chrome regions have to be out of scope. (The repo's recurring footer-`<nav>` collision, in a
  // new costume — here it was the primary nav, not the footer, that the locator over-matched.)
  //
  // ⛔ SCOPED TO THE LEGAL PAIR, AND THAT IS DELIBERATE. `/about` and `/contact` are excluded
  // because a CONTEXTUAL link to either is legitimate and is not what was reported — the FAQ opens
  // with "Can't find what you're looking for? Contact us", which this clause failed on in its
  // first cut and which should obviously stay. Privacy and Terms have no contextual reason to
  // appear in a page body at all: they exist purely as footer chrome, so their presence here IS
  // the duplication, which makes them the honest discriminator between "the footer was reprinted"
  // and "the page links somewhere for a reason".
  for (const href of ["/privacy", "/terms"]) {
    const inPageBody = await page
      .locator(`a[href="${href}"]`)
      .evaluateAll((els) =>
        els.filter((e) => !e.closest("footer") && !e.closest("[data-primary-nav]")).length,
      )
    expect(inPageBody, `/faq reprints the footer link ${href} in its own page body`).toBe(0)
    // …and the footer still carries it, so this is a de-duplication and not a deletion.
    await expect(page.locator(`footer a[href="${href}"]`).first()).toBeVisible()
  }

  // ⛔ NF-TR1 — the record must stay ONE CLICK from this surface. It now lives in the answer a
  // reader asking that question opens, rather than in the removed chrome row. This is the RENDER
  // half of the check; `test_nf_tr1_claim_copy.py` proves the binding, and neither implies the
  // other (its source scan cannot see a link the page fails to render, which is how a first cut
  // of that guard stayed green with the render disabled).
  await page.getByRole("button", { name: /where can i see the record/i }).click()
  await expect(
    page.locator('main a[href="/fantasy/track-record"]').first(),
    "the FAQ no longer reaches the track record from any answer",
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
// NF-C2.1 follow-up — the NFL menu is GROUPED, and the grouping is not stacked on a redundant
// surface header
// ══════════════════════════════════════════════════════════════════════════════════════════════
//
// ⭐ REPORTED (operator, 2026-08-17): twelve NFL items in one flat list, with the two halves of the
// draft engine four rows apart. Asserted in the BROWSER rather than against `nav-model.ts`, because
// the failure that matters is a rendering one: `nav.tsx` suppresses the surface label when it would
// stack on top of section labels, and a source-level read of the model cannot see whether that
// suppression fired, fired too widely, or took the lock icon with it.
test("the NFL menu is grouped by job, and MLB keeps its surface headers", async ({ page }) => {
  // ⚠️ `entitled`, deliberately. The locked branch renders a FLAT list with no sections at all, so
  // on the default (`free`) mock every clause below would pass or fail for a reason that has
  // nothing to do with grouping.
  await signIn(page, { groups: ["subscriber"] })
  await mockApi(page, { entitlement: "entitled" })
  await page.goto("/about")
  await page.waitForLoadState("networkidle")

  const nflTrigger = page.locator("[data-primary-nav] button").filter({ hasText: /^NFL/ }).first()
  await expect(nflTrigger, "the signed-in sub-nav did not render — the seeded session did not take")
    .toBeVisible()
  await nflTrigger.hover()

  // The dropdown is the trigger's sibling inside the hovered `group` wrapper.
  const menu = nflTrigger.locator("xpath=..").locator("div.absolute")
  await expect(menu.getByRole("link", { name: "Mock Draft" })).toBeVisible()
  const text = await menu.innerText()
  // ⚠️ WHOLE LINES, NOT SUBSTRINGS. The first cut asked whether the menu text CONTAINED "DRAFT",
  // which "Mock Draft" and "Draft Optimizer" both satisfy — so the clause passed with every group
  // label deleted and was caught only by the red proof. A section header is its own line.
  const lines = text.split("\n").map((s) => s.trim().toUpperCase())

  // The three groups, in order.
  for (const label of ["RANKINGS & RESEARCH", "DRAFT", "MY LEAGUES"]) {
    expect(lines, `the NFL menu has no "${label}" group — it is a flat list again`).toContain(label)
  }
  expect(lines.indexOf("RANKINGS & RESEARCH")).toBeLessThan(lines.indexOf("DRAFT"))
  expect(lines.indexOf("DRAFT")).toBeLessThan(lines.indexOf("MY LEAGUES"))

  // ⭐ THE ADJACENCY THAT MOTIVATED THE REGROUPING: the practice board and the live board are the
  // two halves of one engine and were four rows apart. Asserted as adjacency, not as an index, so
  // adding an item elsewhere in the menu does not fail this for the wrong reason.
  const links = await menu.getByRole("link").evaluateAll((els) =>
    els.map((e) => (e.textContent ?? "").trim()),
  )
  const mock = links.indexOf("Mock Draft")
  const live = links.indexOf("Draft Optimizer")
  expect(mock, "Mock Draft is missing from the NFL menu").toBeGreaterThanOrEqual(0)
  expect(live, "Draft Optimizer is missing from the NFL menu").toBeGreaterThanOrEqual(0)
  expect(
    Math.abs(mock - live),
    `Mock Draft and Draft Optimizer are ${Math.abs(mock - live)} rows apart: ${links.join(" / ")}`,
  ).toBe(1)

  // ⛔ AND THE SURFACE LABEL IS GONE — it was stacked directly on top of "RANKINGS & RESEARCH".
  expect(
    lines,
    `the NFL menu still prints a redundant FANTASY header above its groups:\n${text}`,
  ).not.toContain("FANTASY")

  // ⭐ THE OTHER SIDE OF THE SUPPRESSION, and the clause that stops it becoming "never show a
  // surface label". MLB's Betting surface OPENS with an unlabelled group — Dashboard, EV Tracker,
  // Props and three more — and only labels its second ("Research"). Its "BETTING" header is
  // therefore the only heading those six items have, and a suppression keyed on "has any labelled
  // section" rather than on "OPENS with one" would silently delete it. Nothing about this menu
  // changed in this story; that is exactly what makes it the control.
  const mlbTrigger = page.locator("[data-primary-nav] button").filter({ hasText: /^MLB/ }).first()
  await mlbTrigger.hover()
  const mlbMenu = mlbTrigger.locator("xpath=..").locator("div.absolute")
  await expect(mlbMenu.getByRole("link", { name: "Dashboard" })).toBeVisible()
  const mlbText = (await mlbMenu.innerText()).toUpperCase()
  expect(
    mlbText.indexOf("BETTING"),
    `the MLB menu lost the "Betting" header its first six items depend on:\n${mlbText}`,
  ).toBeGreaterThanOrEqual(0)
  expect(
    mlbText.indexOf("BETTING"),
    "the Betting header no longer leads its own menu",
  ).toBeLessThan(mlbText.indexOf("DASHBOARD"))
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
  //
  // ⭐ RE-ANCHORED BY NCAAF-P3.9, and the reason is itself the finding. This clause used to NAME the
  // two unshipped products — `/ncaaf|nfl betting/` — and require that no footer link matched. That
  // is a proxy for "unshipped" made of product names, and such a proxy rots the moment one of them
  // ships: `/ncaaf/games` went live at P3.2, so a CORRECT footer (a live link) turned this red
  // while the property it defends was perfectly intact. The rule it exists to enforce is
  // structural — NOTHING UNDER THE "Coming this season" SUB-HEADING IS EVER A LINK — so that is
  // what is asserted now, derived from the DOM. Strictly stronger (it covers every future row,
  // named or not) and it cannot go stale on the next launch.
  //
  // ⚠️ IT MUST STILL SAY THE GROUP IS NON-EMPTY, or a footer that shipped every product would
  // satisfy "no coming row is a link" vacuously.
  expect(text).toContain("coming this season")
  const coming = await footer.locator('nav[aria-label="Products"] li').evaluateAll((els) => {
    const heading = els.findIndex((e) => /coming this season/i.test(e.textContent ?? ""))
    return els
      .slice(heading + 1)
      .map((e) => ({ text: (e.textContent ?? "").trim(), links: e.querySelectorAll("a").length }))
  })
  expect(coming.length, "the 'Coming this season' group is empty — this clause would be vacuous")
    .toBeGreaterThan(0)
  expect(
    coming.filter((r) => r.links > 0).map((r) => r.text),
    "a product listed as 'Coming this season' is rendered as a link",
  ).toEqual([])

  // ⭐ THE ALIGNMENT BUG (operator report + screenshot, 2026-08-09), as a structural assertion.
  // Each coming row used to carry its OWN "Coming this season" chip beside the label in a
  // `flex-wrap`. The Products column is ~250px at `md`: that fits "NFL Betting Intelligence" plus
  // its chip but NOT "NCAAF Betting Intelligence", so one row wrapped its chip to a second line
  // and the other did not — ragged, and it read as broken layout. Hoisting the status to a shared
  // sub-heading makes the wrap structurally impossible. ONE occurrence is the tell that it is a
  // sub-heading rather than a per-row chip, which is the actual fix; a count check survives
  // restyling in a way a pixel assertion would not.
  const statusCount = (text.match(/coming this season/g) ?? []).length
  expect(statusCount, "the coming-soon status is repeated per row, so it can wrap again").toBe(1)
})
