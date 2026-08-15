import { expect, test, type Page } from "@playwright/test"
import { SIGNED_OUT_NAV } from "@/lib/positioning-copy"
import { collectPageErrors, mockApi } from "../support/api-mock"
import { signIn } from "../support/session"
import { expectNoPageErrors } from "../support/assertions"

/**
 * E9.64 — WHO CAN OPEN WHAT, asserted where the answer is actually decided.
 *
 * ══ WHY THIS FILE EXISTS: G100-D0-R1 ITEM 5 ═══════════════════════════════════════════════════
 *
 * `free-league.spec.ts` already carries "a logged-out visitor is not offered the league surfaces",
 * and its own comment records that the assertion is OVER-DETERMINED: the requirement is met one
 * level up by `showSubNav = authenticated || isSignedIn` (`components/nav.tsx:93`), which withholds
 * the ENTIRE sport sub-nav from an anonymous visitor. So `lockedVisibleItems` can be broken in
 * either direction and that spec stays green, because the menu that would carry the items is not in
 * the DOM at all. Both breaks are registered in `red-proof.mjs` as DECLARED-GREEN cases.
 *
 * That is an honest record of a spec that cannot fail, and it is not coverage. R1 named it: nothing
 * anywhere guards the league nav items against an anonymous visitor, and the protection we DO have
 * is incidental — a future story that renders the sport menu logged-out removes it silently.
 *
 * ⭐ THE FIX IS TO ANCHOR ON THE GATE THAT ACTUALLY RUNS. For an anonymous visitor the nav does not
 * reach `surfaceItems`/`freeSignedIn` at all; it renders `SIGNED_OUT_NAV` (`lib/positioning-copy.ts`)
 * — an AUTHORED list, and since E9.60 the only thing that decides what a stranger is offered. That
 * list is falsifiable in the way the old anchor was not: put a gated href in it and the logged-out
 * nav really does grow a link into a wall. `nav-offers-a-gated-league-surface` in `red-proof.mjs`
 * does exactly that and this file goes RED — which is precisely the future the operator described,
 * reproduced rather than reasoned about.
 *
 * ══ AND THE OTHER HALF: NOT OFFERED ≠ NOT REACHABLE ═══════════════════════════════════════════
 *
 * A nav assertion says nothing about someone who follows a shared link, a bookmark or a search
 * result. The route guards are the load-bearing gate, and for the three `FantasyLeagueGuard`
 * surfaces (My League, Import, League Settings) NOTHING anywhere drove them anonymously —
 * `freemium-board.spec.ts` covers only the `FantasyGuard` trio. Both halves are below.
 *
 * ⚠️ THIS PROVES RENDER BEHAVIOUR, NEVER AUTHORIZATION. The tokens `signIn` seeds are unsigned and
 * the API is mocked; who may READ what is enforced server-side and asserted against the real ASGI
 * app in `test_freemium_tier.py` / `test_g100_c1_free_league.py`. A browser test that appeared to
 * check entitlement would be the most convincing vacuous guard in the repo — see `session.ts`.
 */

/** Every fantasy surface that is NOT free-for-everyone, with the gate each one is behind. */
const GATED_SURFACES = [
  // `FantasyGuard` — fantasy entitlement (subscriber / admin / fantasy_comp).
  { label: "League Board", path: "/fantasy/league-board", gate: "entitlement" },
  { label: "Draft Optimizer", path: "/fantasy/draft", gate: "entitlement" },
  { label: "My Teams", path: "/fantasy/my-teams", gate: "entitlement" },
  // `FantasyLeagueGuard` — signed in, with a personalization quota. Free accounts have one.
  { label: "My League", path: "/fantasy/my-league", gate: "account" },
  { label: "Roster Report", path: "/fantasy/roster-report", gate: "account" },
  { label: "Import League", path: "/fantasy/import", gate: "account" },
  { label: "League Settings", path: "/fantasy/league-settings", gate: "account" },
] as const

/** The MLB fantasy surfaces, `restrict: "admin"` while in development. Gated for the same purpose,
 *  so a stranger must not be offered them either — and they are the likeliest to be widened by
 *  accident, because opening the surface up is a one-line nav-model edit. */
const ADMIN_ONLY_HREFS = [
  "/fantasy/mlb/prospects",
  "/fantasy/mlb/disagreements",
  "/fantasy/mlb/league",
] as const

const GATED_HREFS = [...GATED_SURFACES.map((s) => s.path), ...ADMIN_ONLY_HREFS]

/** Hrefs rendered anywhere in the document — nav, body and footer alike.
 *
 *  ⭐ WHOLE-DOCUMENT ON PURPOSE. Scoping to `nav` would miss the same defect arriving through the
 *  footer or a page block, and "a stranger is offered a link into a wall" is the same failure
 *  wherever it is drawn. It also means this cannot be satisfied by moving a link out of the nav. */
async function renderedHrefs(page: Page): Promise<string[]> {
  return page
    .locator("a[href]")
    .evaluateAll((els) =>
      els.map((e) => ((e as HTMLAnchorElement).getAttribute("href") ?? "").split(/[?#]/)[0]),
    )
}

/**
 * A guard's refusal is a `router.push` — it does not vary with viewport, so running it on both
 * projects doubles the job's cost and proves nothing twice. Only the NAV assertion below is
 * genuinely viewport-dependent (the bar and the phone menu draw different subsets of one authored
 * list), which is why this file is in the `mobile` project at all.
 */
// ⚠️ Keyed on the `isMobile` FIXTURE, not on the project NAME. A describe-level `test.skip`
// receives the fixtures only — there is no `testInfo` second parameter there, and reaching for one
// throws `Cannot read properties of undefined` inside every test in the group, which reads as 38
// application failures. `isMobile` is also the honest predicate: it names the viewport capability
// the branch actually depends on rather than a project label that could be renamed.
const skipOnMobile = () =>
  test.skip(
    ({ isMobile }) => !!isMobile,
    "viewport-independent — a guard redirect is the same on every screen",
  )

test.describe("the logged-out nav offers nothing a stranger cannot open", () => {
  // The public fantasy surfaces are where a stranger actually lands (indexed board, shared player
  // link), so that is where the nav has to be right. Both are checked because they are separate
  // pages passing `authenticated={!!accessToken}` independently.
  for (const landing of ["/fantasy/rankings", "/fantasy/projections"] as const) {
    test(`${landing}: no entitlement-gated fantasy surface is offered`, async ({
      page,
      isMobile,
    }) => {
      const errors = collectPageErrors(page)
      await mockApi(page, { entitlement: "free" })
      await page.goto(landing)
      await expect(page.locator("table tbody tr").first()).toBeVisible()

      // ── NON-VACUITY, and it has to be measured rather than assumed ──────────────────────────
      //
      // Three `toHaveCount(0)`s are satisfied perfectly by a page that rendered nothing, which is
      // the shape this repo keeps getting caught by. So: count the SIGNED_OUT_NAV entries actually
      // drawn and require the number this viewport is supposed to draw. The desktop bar renders
      // only the `desktop` subset; the phone menu renders the full set once opened. Asserting the
      // exact figure is what makes "the menu opened" an answered question instead of a hope.
      if (isMobile) await page.getByRole("button", { name: "Toggle menu" }).click()
      const expected = isMobile
        ? SIGNED_OUT_NAV.length
        : SIGNED_OUT_NAV.filter((i) => i.desktop).length
      // `[data-primary-nav]`, never a bare `nav` — `SiteFooter` wraps each of its columns in a
      // `<nav>` too, which this repo has been bitten by three times (see the handle's own comment).
      //
      // ⚠️ `{ visible: true }` IS LOAD-BEARING, and the count is what surfaced it: the desktop bar
      // is `hidden … sm:block`, i.e. still in the DOM on a phone, so a plain DOM count reads 3 + 6 = 9
      // there and matches NEITHER viewport's authored subset. Visibility is also the honest question
      // — "rendered in the DOM" is not "offered to the visitor".
      const navLinks = page
        .locator("[data-primary-nav] a[data-signed-out-nav]")
        .filter({ visible: true })
      await expect(
        navLinks,
        "the logged-out nav did not render its own link set — every absence below would be vacuous",
      ).toHaveCount(expected)

      // ── THE PROPERTY ITSELF ─────────────────────────────────────────────────────────────────
      const hrefs = await renderedHrefs(page)
      for (const gated of GATED_HREFS) {
        expect(
          hrefs,
          `${gated} was offered to a visitor who cannot open it — the link's only behaviour is a ` +
            `redirect, which is a menu that lies about what it opens`,
        ).not.toContain(gated)
      }

      // …and the counterpart, so this file cannot be satisfied by a nav that offers NOTHING: the
      // free board a stranger came for is still one click away.
      expect(hrefs, "the free board is not reachable from the logged-out nav").toContain(
        "/fantasy/rankings",
      )
      expectNoPageErrors(errors)
    })
  }
})

test.describe("a stranger who follows a direct link is refused, and told where to go", () => {
  skipOnMobile()

  for (const surface of GATED_SURFACES) {
    test(`${surface.label} refuses a stranger who follows a direct link`, async ({ page }) => {
      // ⭐ THE HALF A NAV ASSERTION CANNOT REACH. A bookmark, a shared link and a search result all
      // arrive here without ever seeing the nav. For the three `account`-gated surfaces nothing
      // anywhere drove this before — `freemium-board.spec.ts` covers the `entitlement` trio only.
      await mockApi(page, { entitlement: "free" })
      await page.goto(surface.path)

      await page.waitForURL((url) => !url.pathname.startsWith(surface.path), { timeout: 10_000 })
      expect(page.url(), `${surface.label} rendered for a stranger`).not.toContain(surface.path)

      // ⭐ WHERE it sends them is a product decision with money attached, so it is asserted rather
      // than waved through. A stranger needs an ACCOUNT: sending them to /subscribe asks them to
      // pay for something the free tier includes. `?next=` is the other half — E9.58 shipped bare
      // `/login` bounces, so a visitor who signed up landed on /dashboard with no trace of where
      // they had been going.
      const url = new URL(page.url())
      expect(url.pathname, `${surface.label} sent a stranger somewhere other than sign-in`).toBe(
        "/login",
      )
      expect(
        url.searchParams.get("next"),
        `${surface.label} dropped the destination, so signing up strands the visitor`,
      ).toBe(surface.path)
    })
  }
})

test.describe("a signed-in FREE account gets the free tier and is upsold the rest", () => {
  skipOnMobile()

  for (const surface of GATED_SURFACES.filter((s) => s.gate === "account")) {
    test(`${surface.label} opens for a free account`, async ({ page }) => {
      // The free tier's whole premise. Gating these on fantasy entitlement would 403 exactly the
      // users it exists for, and the failure is silent: the page simply redirects.
      await signIn(page, { groups: [] })
      await mockApi(page, { entitlement: "free", leagues: "one" })
      await page.goto(surface.path)

      // Auto-retrying, deliberately: `AuthContext` restores the session in an effect that runs
      // AFTER `page.goto` resolves, so a single-shot read races the guard's own decision.
      await expect(
        page.locator("h1, h2").first(),
        `${surface.label} never rendered for a free account`,
      ).toBeVisible()
      expect(page.url(), `${surface.label} bounced a free account`).toContain(surface.path)
    })
  }

  for (const surface of GATED_SURFACES.filter((s) => s.gate === "entitlement")) {
    test(`${surface.label} upsells a free account rather than bouncing it to sign in`, async ({
      page,
    }) => {
      // ⭐ THE DISTINCTION THAT COSTS MONEY IF IT INVERTS, and it mirrors the server's 401-vs-403.
      // This account HAS an account; what it lacks is a membership, so /login is a dead end that
      // asks them to do something they have already done. Nothing anywhere asserted this.
      await signIn(page, { groups: [] })
      await mockApi(page, { entitlement: "free", leagues: "one" })
      await page.goto(surface.path)

      await page.waitForURL((url) => !url.pathname.startsWith(surface.path), { timeout: 10_000 })
      expect(
        new URL(page.url()).pathname,
        `${surface.label} sent a signed-in free account to sign in again instead of to the upsell`,
      ).toBe("/subscribe")
    })
  }
})

test.describe("a subscriber gets the whole surface", () => {
  skipOnMobile()

  for (const surface of GATED_SURFACES) {
    test(`${surface.label} opens for a subscriber`, async ({ page }) => {
      // ⛔ WITHOUT THIS BLOCK THE FILE IS SATISFIED BY GATING EVERYTHING. Every assertion above is
      // some form of "this is refused"; a build that locked the product away entirely would pass
      // all of them and the suite would be green with nothing sold. This is the only block whose
      // failure means the opposite of the others'.
      const errors = collectPageErrors(page)
      await signIn(page, { groups: ["subscriber"] })
      await mockApi(page, { entitlement: "entitled", leagues: "one" })
      await page.goto(surface.path)

      await expect(
        page.locator("h1, h2").first(),
        `${surface.label} never rendered for a subscriber`,
      ).toBeVisible()
      expect(page.url(), `${surface.label} bounced a subscriber`).toContain(surface.path)
      expectNoPageErrors(errors)
    })
  }

  test("the sport menu carries the gated surfaces once there is an account to use them", async ({
    page,
  }) => {
    // The mirror of the anonymous case, and it is what stops "offer a stranger nothing" being
    // satisfied by offering NOBODY anything — a feature that exists and cannot be found.
    await signIn(page, { groups: ["subscriber"] })
    await mockApi(page, { entitlement: "entitled", leagues: "one" })
    await page.goto("/fantasy/rankings")

    for (const surface of GATED_SURFACES) {
      await expect(
        page.locator(`a[href="${surface.path}"]`),
        `${surface.label} is unreachable from the nav for a subscriber`,
      ).not.toHaveCount(0)
    }
  })
})
