import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { expect, test } from "@playwright/test"
import { mockApi } from "../support/api-mock"
import { buildEnv } from "../support/env"

/**
 * E9.63 — the E9.58 signup funnel.
 *
 * E9.58 shipped 2026-08-06 and produced six defects. Every one was found by the operator, by hand,
 * in a browser; not one was visible to `tsc`, `eslint` or `next build`. Two of them are structural
 * enough to be worth locking down here, and they are the two this file is built around:
 *
 *   · THE HOSTED-UI HOST WAS DNS-DEAD IN PRODUCTION. Three files each carried a DIFFERENT invented
 *     host; none resolved; there was zero working signup in prod. See `@live` at the bottom for
 *     the only part of that a test can honestly reach, and `e2e/README.md` for why the rest is an
 *     operator check.
 *   · THE LOGGED-OUT MOBILE NAV HAD NO SIGNUP AFFORDANCE — the whole block was `hidden sm:flex`.
 *     A desktop-only suite is structurally blind to that, which is why this spec (alone) also runs
 *     on the `mobile` project. Two viewports, one file, on purpose.
 *
 * ⛔ NOT MOCKED HERE: Cognito, Google, Stripe, PostHog. This drives the REAL rendered funnel and
 * stops at the redirect out. See the README's "The boundary".
 */

/** Every page a visitor can start a signup from. */
const ENTRY_POINTS = [
  { path: "/signup", why: "the front door E9.58 built" },
  { path: "/subscribe", why: "where every locked CTA lands" },
  { path: "/login", why: "the pre-E9.58 entry, still the only one a returning user knows" },
] as const

const GOOGLE_CTA = "Continue with Google"

for (const entry of ENTRY_POINTS) {
  test(`${entry.path} offers a working Google entry (${entry.why})`, async ({ page }) => {
    await mockApi(page)
    await page.goto(entry.path)

    const cta = page.getByRole("button", { name: GOOGLE_CTA })
    await expect(cta).toBeVisible()
    await expect(cta).toBeEnabled()
  })
}

test("the nav carries a signup affordance for a logged-out visitor", async ({ page }, testInfo) => {
  await mockApi(page, { entitlement: "locked" })
  // Start on a locked surface, not the homepage: that is where an indexed search result drops a
  // stranger, and it is the nav on THAT page that has to offer them a way in.
  await page.goto("/fantasy/projections")

  const navSignup = page.getByRole("link", { name: /sign up/i })
  const visible = navSignup.filter({ visible: true })

  if ((await visible.count()) === 0) {
    // Small viewports may keep it behind the hamburger. Open it and look again — but only after
    // failing to find it in the bar, so a regression that hides it entirely still fails.
    const hamburger = page.locator("nav button").last()
    if (await hamburger.isVisible()) await hamburger.click()
  }

  const found = page.getByRole("link", { name: /sign up/i }).filter({ visible: true }).first()
  await expect(
    found,
    `no reachable "Sign Up" affordance at ${testInfo.project.name} viewport`,
  ).toBeVisible()
  expect(await found.getAttribute("href")).toBe("/signup")
})

test("the signup route the nav points at actually renders the Google entry", async ({ page }) => {
  // The nav link and the page it lands on are two separate facts. E9.58's own defect list has an
  // entry for each kind (a missing affordance; a present affordance behind a dead host), so
  // asserting the link exists is not the same as asserting the funnel is walkable.
  await mockApi(page)
  await page.goto("/signup")
  await expect(page.getByRole("button", { name: GOOGLE_CTA })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible()
})

test("clicking Continue with Google leaves for the Cognito authorize endpoint", async ({
  page,
  baseURL,
}) => {
  await mockApi(page)

  // Intercept the outbound redirect rather than following it — the E2E build's Hosted-UI host is
  // deliberately fake (see e2e/e2e.env), and the assertion worth making is about the URL the app
  // constructs, not about what a real IdP would answer.
  //
  // ⚠️ Answer 204, do NOT abort. A browser treats "No Content" on a top-level navigation as
  // "stay where you are", so the document — and its localStorage, which the next test reads — is
  // still ours. An `abort()` leaves the tab on `about:blank`, whose origin is `null` and whose
  // storage access throws `SecurityError`; both of the assertions below then fail for a reason
  // that has nothing to do with the app.
  let authorizeUrl: string | null = null
  await page.route(/\/oauth2\/authorize/, (route) => {
    authorizeUrl = route.request().url()
    return route.fulfill({ status: 204, body: "" })
  })

  await page.goto("/signup")
  await page.getByRole("button", { name: GOOGLE_CTA }).click()
  await expect
    .poll(() => authorizeUrl, { message: "the Google button never navigated anywhere" })
    .not.toBeNull()

  const url = new URL(authorizeUrl!)
  // ⭐ The app must send the user to the host it was CONFIGURED with — read from the same
  // `e2e/e2e.env` the build sourced, because a `NEXT_PUBLIC_*` value is inlined at build time and
  // is not visible to this process. That is the shape of the E9.58 outage: three files each
  // carried a different invented host, and the one that reached Vercel resolved to nothing. This
  // cannot tell a correct host from a wrong one (see `@live` below) — it can insist the app never
  // substitutes a host of its own for the configured one.
  expect(url.host).toBe(buildEnv("NEXT_PUBLIC_COGNITO_HOSTED_UI_DOMAIN"))
  expect(url.searchParams.get("client_id")).toBe(buildEnv("NEXT_PUBLIC_COGNITO_APP_CLIENT_ID"))
  expect(url.pathname).toBe("/oauth2/authorize")
  expect(url.searchParams.get("identity_provider")).toBe("Google")
  expect(url.searchParams.get("response_type")).toBe("code")
  expect(url.searchParams.get("code_challenge_method")).toBe("S256")
  expect(url.searchParams.get("code_challenge")).toBeTruthy()
  expect(url.searchParams.get("state")).toBeTruthy()
  // The redirect must come back to US, or the round trip drops the user on someone else's origin.
  expect(url.searchParams.get("redirect_uri")).toContain(new URL(baseURL!).origin)
})

test("a signup started from /subscribe carries the return destination", async ({ page }) => {
  // E9.58's stated reason for `?next=`: a visitor who came to sign up in order to BUY must land
  // back on /subscribe, not be dumped on /dashboard having lost the thing they came for. The
  // destination is stashed in localStorage across the redirect, so that is where to read it.
  await mockApi(page)
  await page.route(/\/oauth2\/authorize/, (route) => route.fulfill({ status: 204, body: "" }))

  await page.goto("/signup?next=%2Fsubscribe")
  await page.getByRole("button", { name: GOOGLE_CTA }).click()

  await expect
    .poll(async () =>
      page.evaluate(() =>
        Object.keys(localStorage)
          .map((k) => localStorage.getItem(k))
          .filter((v) => v === "/subscribe").length,
      ))
    .toBeGreaterThan(0)
})

/**
 * ══ @live — excluded from the hermetic gate; run with `npm run test:e2e:live` ═══════════════════
 *
 * The one thing a hermetic suite structurally cannot check about E9.58's worst defect: whether the
 * configured Hosted-UI host EXISTS. That bug was not a code error — every file was internally
 * consistent, `tsc` was happy, the button rendered and the click fired. The host simply did not
 * resolve, so the browser died on DNS and prod had no working signup at all.
 *
 * Needs the REAL value, which is not in the E2E build. Read from the environment, else from
 * `.env.local` (gitignored, present on the operator's machine); skip loudly if neither has it —
 * a check that cannot run is never scored as a pass.
 */
function prodHostedUiDomain(): string | null {
  if (process.env.PROD_COGNITO_HOSTED_UI_DOMAIN) return process.env.PROD_COGNITO_HOSTED_UI_DOMAIN
  const envLocal = join(process.cwd(), ".env.local")
  if (!existsSync(envLocal)) return null
  const line = readFileSync(envLocal, "utf8")
    .split("\n")
    .find((l) => l.trim().startsWith("NEXT_PUBLIC_COGNITO_HOSTED_UI_DOMAIN="))
  const value = line?.split("=").slice(1).join("=").trim()
  return value || null
}

test("@live the production Cognito Hosted-UI host resolves and answers", async ({ request }) => {
  const domain = prodHostedUiDomain()
  test.skip(
    !domain,
    "set PROD_COGNITO_HOSTED_UI_DOMAIN (or put the real value in frontend/.env.local) to run this",
  )

  // A bare GET on /oauth2/authorize without params answers 400 from a LIVE Cognito domain — which
  // is a pass here. The failure being ruled out is DNS/connection, not a status code.
  const res = await request.get(`https://${domain}/oauth2/authorize`, {
    failOnStatusCode: false,
    timeout: 15_000,
  })
  expect(res.status(), `${domain} did not answer`).toBeGreaterThan(0)
})
