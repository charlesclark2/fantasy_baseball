import { expect, test } from "@playwright/test"
import { mockApi } from "../support/api-mock"
import { internalHrefs } from "../support/assertions"

/**
 * E9.63 — EVERY internal link on the public funnel must resolve to a live route.
 *
 * ⭐ THE STORY'S HEADLINE GUARD. E9.56c shipped a primary CTA pointing at `/pricing`, a route that
 * has never existed, and it killed the entire buy path for as long as the free pages were open.
 * Nothing in the toolchain could see it:
 *
 *   · `tsc` type-checks a URL as a string. `"/pricing"` is a perfectly good string.
 *   · `eslint` has no idea what the app's routes are.
 *   · `next build` resolves a `<Link href>` and would have complained — but the CTA was a plain
 *     `<a href>`, and the value came from the API at runtime. Neither is reachable at build time.
 *
 * So this crawler is the only instrument in the repo that can answer "does every link go
 * somewhere". It walks the logged-out funnel, harvests every internal `href` actually PRESENT IN
 * THE RENDERED DOM (which is what makes it catch a runtime-supplied one), and demands a non-4xx.
 */

/** The logged-out funnel: what a stranger who lands on an indexed locked projection can reach. */
const SEEDS = [
  "/",
  "/subscribe",
  "/signup",
  "/login",
  "/fantasy/projections",
  "/fantasy/rankings",
  "/fantasy/track-record",
  "/about",
  "/faq",
  "/terms",
  "/privacy",
  "/contact",
  "/changelog",
]

/**
 * A crawl is only as good as its harvest, and a crawler that finds nothing passes VACUOUSLY —
 * green, fast, and worthless. These floors are the guard on the guard: they are set well below
 * what the funnel actually carries today (measured: 13 seeds, ~60 distinct internal hrefs), so
 * they fail on "the harvest collapsed" without being a churn tax on ordinary link edits.
 */
const MIN_SEEDS_WITH_LINKS = SEEDS.length
const MIN_DISTINCT_HREFS = 20

test.describe("route integrity", () => {
  test("every internal href on the logged-out funnel resolves", async ({ page }) => {
    await mockApi(page, { entitlement: "locked" })

    const found = new Map<string, string[]>() // href -> the pages that link to it
    let seedsWithLinks = 0

    for (const seed of SEEDS) {
      const res = await page.goto(seed)
      expect(res?.status(), `seed page ${seed} did not load`).toBeLessThan(400)
      // The fantasy surfaces render their links only after the payload lands, so give the table a
      // beat — harvesting too early is how a crawler quietly stops covering the pages that matter.
      await page.waitForLoadState("networkidle")

      const hrefs = await internalHrefs(page)
      if (hrefs.length) seedsWithLinks++
      for (const href of hrefs) {
        found.set(href, [...(found.get(href) ?? []), seed])
      }
    }

    expect(seedsWithLinks, "a seed page rendered no internal links at all").toBe(MIN_SEEDS_WITH_LINKS)
    expect(
      found.size,
      "the crawl harvested implausibly few links — it is passing vacuously",
    ).toBeGreaterThanOrEqual(MIN_DISTINCT_HREFS)

    // `request.get` follows redirects, so a route that only exists as a redirect target (`/pricing`
    // → `/subscribe`, the permanent backstop in next.config.mjs) correctly counts as resolving.
    const dead: string[] = []
    for (const [href, sources] of found) {
      const res = await page.request.get(href)
      if (res.status() >= 400) dead.push(`${href}  →  ${res.status()}   (linked from ${sources.join(", ")})`)
    }
    expect(dead, `dead internal link(s):\n${dead.join("\n")}`).toEqual([])

    test.info().annotations.push({
      type: "crawl",
      description: `${found.size} distinct internal hrefs across ${SEEDS.length} seed pages`,
    })
  })

  test("`/pricing` still resolves — the historical dead CTA", async ({ page }) => {
    // Kept as its own named case rather than left implicit in the crawl. `/pricing` is not linked
    // from anywhere in the repo any more (E9.56c repointed every link to `/subscribe`), so the
    // crawl above would not exercise it — yet the deployed API still hands it out as
    // `upgrade.ctaHref` until the next `deploy.sh`, and it is also simply the URL people type.
    // Deleting the redirect would be silent and immediate.
    const res = await page.request.get("/pricing")
    expect(res.status()).toBeLessThan(400)
    expect(new URL(res.url()).pathname).toBe("/subscribe")
  })

  test("a route that genuinely does not exist returns 404", async ({ page }) => {
    // The crawler's own calibration. If Next served a 200 shell for unknown paths — a plausible
    // config change — every assertion above would pass no matter how many links were dead.
    const res = await page.request.get("/this-route-does-not-exist-e9-63")
    expect(res.status(), "unknown routes do not 404 — the crawler cannot detect a dead link").toBe(
      404,
    )
  })
})
