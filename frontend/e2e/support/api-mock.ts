import { readFileSync } from "node:fs"
import { join } from "node:path"
import type { Page, Request, Route } from "@playwright/test"

/**
 * E9.63 — hermetic API + third-party interception.
 *
 * The E2E build is compiled with `NEXT_PUBLIC_API_URL=/__e2e-api` (see `e2e/e2e.env` for why the
 * base must be SAME-ORIGIN — the shipped CSP blocks any other host before Playwright can route
 * it). An API call this file fails to intercept therefore cannot reach production; it lands on the
 * local Next server as a 404 and shows up as a visible failure rather than a test that quietly
 * passes against live data.
 */

export const API_PREFIX = "/__e2e-api"

const FIXTURE_DIR = join(process.cwd(), "e2e", "fixtures", "api")

function fixture<T = any>(name: string): T {
  return JSON.parse(readFileSync(join(FIXTURE_DIR, name), "utf8"))
}

/**
 * E9.59 — the public pricing payload, minus its provenance annotation, so what the page
 * receives is exactly the API's own shape. The `__`-prefixed key documents why this one
 * fixture is synthetic (the route is not live in prod yet, so it cannot be captured); it
 * is not part of the contract and must never reach the page.
 */
function publicPricingFixture() {
  const raw = fixture<Record<string, unknown>>("subscription-public-pricing.synthetic.json")
  return Object.fromEntries(Object.entries(raw).filter(([k]) => !k.startsWith("__")))
}

export const FIXTURES = {
  publicPricing: publicPricingFixture,
  projectionsLocked: () => fixture("fantasy-nfl-projections-2026-locked.json"),
  projectionsEntitled: () => fixture("fantasy-nfl-projections-2026-entitled.synthetic.json"),
  manifestLocked: () => fixture("fantasy-nfl-manifest-2026-locked.json"),
  boardLocked: () => fixture("fantasy-nfl-board-full_ppr-12-2026-locked.json"),
  trackRecordManifest: () => fixture("fantasy-nfl-track-record-manifest.json"),
  trackRecordSeason: () => fixture("fantasy-nfl-track-record-2025.json"),
}

/** What the fantasy surfaces get back: the locked (anonymous) payload or the entitled one. */
export type Entitlement = "locked" | "entitled"

export type MockOptions = {
  entitlement?: Entitlement
  /** Last-chance mutation of a payload before it is served — used to reproduce a server state we
   *  cannot capture (e.g. the deploy-skew `upgrade.ctaHref: "/pricing"` of E9.56c). */
  transform?: (pathname: string, body: any) => any
}

export type ApiMock = {
  /** Every API path the page asked for. */
  requested: string[]
  /** API paths NO fixture matched — a non-empty list means the page reached for something this
   *  harness does not model, and every assertion downstream of it is suspect. */
  unmatched: string[]
}

function payloadFor(pathname: string, entitlement: Entitlement): unknown | undefined {
  if (pathname === "/fantasy/nfl/projections") {
    return entitlement === "entitled" ? FIXTURES.projectionsEntitled() : FIXTURES.projectionsLocked()
  }
  if (pathname === "/subscription/public-pricing") return FIXTURES.publicPricing()
  if (pathname === "/fantasy/nfl/manifest") return FIXTURES.manifestLocked()
  if (pathname === "/fantasy/nfl/board") return FIXTURES.boardLocked()
  if (pathname === "/fantasy/nfl/track-record/manifest") return FIXTURES.trackRecordManifest()
  if (/^\/fantasy\/nfl\/track-record\/\d{4}$/.test(pathname)) return FIXTURES.trackRecordSeason()
  return undefined
}

/**
 * Install the API mock and the third-party blocks on a page.
 *
 * Returns a live record of what was asked for — assert `unmatched` is empty in any spec whose
 * conclusion depends on the page having got its data.
 */
export async function mockApi(page: Page, options: MockOptions = {}): Promise<ApiMock> {
  const entitlement = options.entitlement ?? "locked"
  const mock: ApiMock = { requested: [], unmatched: [] }

  await page.route(`**${API_PREFIX}/**`, async (route: Route, request: Request) => {
    const url = new URL(request.url())
    // Strip the harness prefix so the fixture map is keyed on the API's OWN paths — the same
    // strings that appear in `app/backend/routers/fantasy.py`.
    const apiPath = url.pathname.slice(url.pathname.indexOf(API_PREFIX) + API_PREFIX.length)
    mock.requested.push(apiPath + url.search)

    let body = payloadFor(apiPath, entitlement)
    if (body === undefined) {
      mock.unmatched.push(apiPath + url.search)
      await route.fulfill({
        status: 501,
        contentType: "application/json",
        body: JSON.stringify({ detail: `e2e: no fixture for ${apiPath}` }),
      })
      return
    }
    if (options.transform) body = options.transform(apiPath, body)

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "access-control-allow-origin": "*" },
      body: JSON.stringify(body),
    })
  })

  await blockThirdParty(page)
  return mock
}

/**
 * Cut every third-party beacon. Sentry's DSN is hardcoded in `instrumentation-client.ts` and
 * PostHog is proxied through the same-origin `/ingest` rewrite, so without this the suite makes
 * real outbound calls from CI — slow, flaky, and it pollutes production analytics with robot
 * traffic.
 */
export async function blockThirdParty(page: Page) {
  for (const pattern of ["**/ingest/**", "**/*.sentry.io/**", "**/*.i.posthog.com/**"]) {
    await page.route(pattern, (route) => route.abort())
  }
}

/** Collect uncaught page errors so a spec can assert the surface rendered without throwing. */
export function collectPageErrors(page: Page): string[] {
  const errors: string[] = []
  page.on("pageerror", (e) => errors.push(String(e)))
  return errors
}
