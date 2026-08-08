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
/**
 * G100-D1 — the CDN read path.
 *
 * An ANONYMOUS caller no longer calls the API Lambda directly: `lib/api.ts::cdnFetch` fetches the
 * same-origin `/api/public/*` route handler, which Vercel serves from the edge (see that handler's
 * module comment). Those requests do NOT carry `API_PREFIX`, so without this map they would slip
 * past the interceptor entirely — and, because they are same-origin, they would land on the local
 * Next server and be answered by the REAL handler, which would then try to reach the real API. A
 * hermetic suite would silently stop being hermetic.
 *
 * Mapping back to the canonical API path (rather than adding a second fixture key space) is what
 * keeps every existing spec working unchanged: `fail: ["/picks/featured"]` and any `transform`
 * keyed on an API path keep meaning exactly what they meant before, regardless of which transport
 * the page happened to use.
 *
 * ⚠️ COVERAGE NOTE: intercepting here means Playwright answers BEFORE the route handler runs, so
 * the handler's own logic is not exercised by the E2E suite. That is deliberate — its contract
 * (never forwards Authorization, allowlist-only, never caches an empty body) is pinned by
 * `betting_ml/tests/test_g100_d1_cost_guardrails.py`, and its actual payoff is CDN behaviour that
 * no browser test can observe anyway.
 */
const CDN_PREFIX = "/api/public"

function cdnPathToApiPath(pathname: string): string | undefined {
  if (!pathname.startsWith(CDN_PREFIX + "/")) return undefined
  const rest = pathname.slice(CDN_PREFIX.length + 1)
  if (rest === "featured") return "/picks/featured"
  if (rest === "manifest") return "/fantasy/nfl/manifest"
  if (rest === "projections") return "/fantasy/nfl/projections"
  if (rest === "board") return "/fantasy/nfl/board"
  if (rest === "track-record/manifest") return "/fantasy/nfl/track-record/manifest"
  if (/^track-record\/\d{4}$/.test(rest)) return `/fantasy/nfl/${rest}`
  return undefined
}

export async function mockApi(page: Page, options: MockOptions = {}): Promise<ApiMock> {
  const entitlement = options.entitlement ?? "locked"
  const mock: ApiMock = { requested: [], unmatched: [] }

  /** Answer one intercepted call, given the canonical API path it resolves to. */
  const fulfil = async (route: Route, apiPath: string, search: string) => {
    mock.requested.push(apiPath + search)

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
      mock.unmatched.push(apiPath + search)
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
  }

  await page.route(`**${API_PREFIX}/**`, async (route: Route, request: Request) => {
    const url = new URL(request.url())
    // Strip the harness prefix so the fixture map is keyed on the API's OWN paths — the same
    // strings that appear in `app/backend/routers/fantasy.py`.
    const apiPath = url.pathname.slice(url.pathname.indexOf(API_PREFIX) + API_PREFIX.length)
    await fulfil(route, apiPath, url.search)
  })

  await page.route(`**${CDN_PREFIX}/**`, async (route: Route, request: Request) => {
    const url = new URL(request.url())
    const apiPath = cdnPathToApiPath(url.pathname)
    if (apiPath === undefined) {
      // An unmapped CDN path is a harness gap, not a pass — surface it the same way an unmatched
      // API path is surfaced rather than letting it reach the real handler.
      mock.unmatched.push(url.pathname + url.search)
      await route.fulfill({
        status: 501,
        contentType: "application/json",
        body: JSON.stringify({ detail: `e2e: unmapped CDN path ${url.pathname}` }),
      })
      return
    }
    await fulfil(route, apiPath, url.search)
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
