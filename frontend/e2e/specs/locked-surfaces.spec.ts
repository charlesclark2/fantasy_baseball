import { expect, test } from "@playwright/test"
import { collectPageErrors, mockApi } from "../support/api-mock"
import {
  LOCK_CHIP,
  expectApiFullyMocked,
  expectLockChipInEveryRow,
  expectNoNaN,
  expectNoPageErrors,
} from "../support/assertions"

/**
 * E9.63 — the LOCKED (logged-out / non-subscriber) fantasy surfaces.
 *
 * This file is the E9.56b regression, written down. That cluster shipped past `tsc`, `eslint` and
 * `next build` because none of them renders a page:
 *
 *   · Rankings rendered BLANK for every free visitor — `p.pts != null` (a filter that exists to
 *     hide an unprojected gap-fill K/DST) drops all 858 rows of a locked board, because a locked
 *     row carries no `pts` at all.
 *   · Sorting a locked board by rank evaluates `undefined - undefined` → `NaN`.
 *   · The primary CTA pointed at `/pricing`, a route that has never existed.
 *
 * Each is asserted here against the REAL prod locked payloads (`e2e/fixtures/api/`, captured
 * anonymously — see `capture-fixtures.mjs`), because each is invisible to every other gate we run.
 */

const SURFACES = [
  {
    name: "Projections",
    path: "/fantasy/projections",
    heading: "Season Projections",
    // A column that is unambiguously model output — the one a locked row can never legitimately
    // fill in. Asserted per-ROW, not counted page-wide: see `expectLockChipInEveryRow`.
    modelColumn: "Proj",
  },
  {
    name: "Rankings",
    path: "/fantasy/rankings",
    heading: "Rankings",
    modelColumn: "Proj pts",
  },
] as const

for (const surface of SURFACES) {
  test.describe(`locked ${surface.name}`, () => {
    test("renders rows, not a blank page", async ({ page }) => {
      const errors = collectPageErrors(page)
      const mock = await mockApi(page, { entitlement: "locked" })

      await page.goto(surface.path)
      await expect(page.getByRole("heading", { name: surface.heading })).toBeVisible()

      // THE E9.56b BUG. A locked board carries 858 rows; the broken filter rendered zero. The page
      // still looked "fine" — heading, chrome, footer, no error — which is why only a rendered-row
      // count catches it.
      const rows = page.locator("table tbody tr")
      await expect(rows.first()).toBeVisible()
      expect(await rows.count(), "locked board rendered no rows").toBeGreaterThan(20)

      expectApiFullyMocked(mock)
      expectNoPageErrors(errors)
    })

    test("every withheld value carries a lock chip, and nothing renders NaN", async ({ page }) => {
      const mock = await mockApi(page, { entitlement: "locked" })
      await page.goto(surface.path)
      await expect(page.locator("table tbody tr").first()).toBeVisible()

      // A withheld value must be visibly WITHHELD. The failure this rules out is subtler than a
      // blank page: a locked cell falling through to "—" reads as "we have nothing for this
      // player" rather than "subscribe to see it" — an honest-absence rendering standing in for a
      // gating one (E9.56c fixed exactly that in two columns).
      await expectLockChipInEveryRow(page, surface.modelColumn)

      await expectNoNaN(page)
      expectApiFullyMocked(mock)
    })

    test("the subscribe CTA is present and points at a route that exists", async ({ page }) => {
      const mock = await mockApi(page, { entitlement: "locked" })
      await page.goto(surface.path)

      const cta = page.getByRole("link", { name: "Subscribe to unlock" }).first()
      await expect(cta).toBeVisible()

      const href = await cta.getAttribute("href")
      expect(href).toBeTruthy()
      const res = await page.request.get(href!)
      expect(res.status(), `the primary conversion CTA points at ${href}`).toBeLessThan(400)

      expectApiFullyMocked(mock)
    })

    test("a lock chip itself links somewhere real", async ({ page }) => {
      await mockApi(page, { entitlement: "locked" })
      await page.goto(surface.path)

      const chip = page.locator(LOCK_CHIP).first()
      await expect(chip).toBeVisible()
      const href = await chip.getAttribute("href")
      expect(href, "a lock chip with no href is a padlock that does nothing").toBeTruthy()
      expect((await page.request.get(href!)).status()).toBeLessThan(400)
    })
  })
}

test.describe("locked Projections — server-supplied CTA target", () => {
  /**
   * ⭐ THE DEPLOY-SKEW CASE, and the one no build step can reach.
   *
   * `upgrade.ctaHref` is chosen by the API, and the API Lambda ships only via a manual
   * `deploy.sh` — so a frontend deployed today can be talking to a backend that still sends the
   * old `/pricing`. That is not hypothetical: it is what happened, and the whole buy path was a
   * 404 for as long as the free pages were open.
   *
   * `resolveUpgradeHref` maps the server's value through an allowlist for precisely this window.
   * Here the fixture is mutated to send the stale value, and the assertion is that the RENDERED
   * link still resolves. A server-controlled link target is otherwise a server-controlled outage.
   */
  test("a stale `/pricing` from the API still renders a CTA that resolves", async ({ page }) => {
    const mock = await mockApi(page, {
      entitlement: "locked",
      transform: (pathname, body) => {
        if (pathname === "/fantasy/nfl/projections") {
          return { ...body, upgrade: { ...(body.upgrade ?? {}), ctaHref: "/pricing" } }
        }
        return body
      },
    })

    await page.goto("/fantasy/projections")
    const cta = page.getByRole("link", { name: "Subscribe to unlock" }).first()
    await expect(cta).toBeVisible()

    const href = await cta.getAttribute("href")
    expect(await (await page.request.get(href!)).status()).toBeLessThan(400)
    expectApiFullyMocked(mock)
  })

  test("an unrecognized CTA target from the API is not trusted verbatim", async ({ page }) => {
    // The allowlist's real job: an arbitrary server value must not become the rendered href.
    await mockApi(page, {
      entitlement: "locked",
      transform: (pathname, body) =>
        pathname === "/fantasy/nfl/projections"
          ? { ...body, upgrade: { ...(body.upgrade ?? {}), ctaHref: "/route-that-does-not-exist" } }
          : body,
    })

    await page.goto("/fantasy/projections")
    const cta = page.getByRole("link", { name: "Subscribe to unlock" }).first()
    await expect(cta).toBeVisible()
    expect(await cta.getAttribute("href")).not.toBe("/route-that-does-not-exist")
    expect(await (await page.request.get((await cta.getAttribute("href"))!)).status()).toBeLessThan(
      400,
    )
  })
})
