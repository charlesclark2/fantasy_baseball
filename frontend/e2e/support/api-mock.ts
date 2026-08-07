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

export const FIXTURES = {
  // E9.59. Was synthetic while the route was un-deployed; a REAL capture since 2026-08-07,
  // once the API-Gateway `NONE` route went live. ⚠️ Its amount is now the true $10, so the
  // "a price renders" spec no longer discriminates a hardcoded price — the `transform` spec
  // (which changes the SERVER's amount and demands the DOM follow) is what carries that, and
  // it is immune to whatever this fixture holds.
  publicPricing: () => fixture("subscription-public-pricing.json"),
  projectionsLocked: () => fixture("fantasy-nfl-projections-2026-locked.json"),
  projectionsEntitled: () => fixture("fantasy-nfl-projections-2026-entitled.synthetic.json"),
  manifestLocked: () => fixture("fantasy-nfl-manifest-2026-locked.json"),
  boardLocked: () => fixture("fantasy-nfl-board-full_ppr-12-2026-locked.json"),
  trackRecordManifest: () => fixture("fantasy-nfl-track-record-manifest.json"),
  trackRecordSeason: () => fixture("fantasy-nfl-track-record-2025.json"),
  // E9.46 — the home page's live model-vs-market element. A verbatim public capture; ⚠️ its
  // CONTENT changes every day (it is whichever game currently has the widest gap), so
  // `home-positioning.spec.ts` asserts against the payload's OWN values and never a literal.
  featuredPick: () => fixture("picks-featured.json"),
}

/** What the fantasy surfaces get back: the locked (anonymous) payload or the entitled one. */
export type Entitlement = "locked" | "entitled"

export type MockOptions = {
  entitlement?: Entitlement
  /** Last-chance mutation of a payload before it is served — used to reproduce a server state we
   *  cannot capture (e.g. the deploy-skew `upgrade.ctaHref: "/pricing"` of E9.56c). */
  transform?: (pathname: string, body: any) => any
  /**
   * API paths to answer with a 5xx instead of a fixture — the READ ITSELF failing, which
   * `transform` structurally cannot express (it rewrites a body that was successfully served).
   *
   * ⭐ E9.46 needs it because "the model published nothing today" and "this page could not reach
   * the model" are DIFFERENT FACTS that the home page states differently, and a harness that can
   * only produce the first can only ever test half of that. Registered here rather than as a
   * spec-local `page.route` override so the call still lands in `requested` — an override would
   * make the request invisible to `expectApiFullyMocked`, i.e. a failure path that looks to the
   * harness like a page that never asked for anything.
   */
  fail?: string[]
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
  if (pathname === "/picks/featured") return FIXTURES.featuredPick()
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

    if (options.fail?.includes(apiPath)) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "e2e: deliberate read failure" }),
      })
      return
    }

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
