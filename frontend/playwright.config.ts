import { defineConfig, devices } from "@playwright/test"

/**
 * E9.63 — the frontend E2E smoke harness.
 *
 * SCOPE (deliberately minimal — see `e2e/README.md`): the launch-critical funnel only. This exists
 * to catch the class of defect that ships PAST `tsc` + `eslint` + `next build` — a blank render, a
 * `NaN` column, a CTA pointing at a route that does not exist, a missing signup affordance. It is
 * NOT a coverage suite; E9.64/E9.65 add specs to THIS harness rather than rebuilding it.
 *
 * TARGET: a production build served by `next start`. Not `next dev` — the E9.56c `/pricing` 404 was
 * a routing fact, and dev-server routing is not the routing that ships.
 *
 * NETWORK: hermetic. Every call to the API base is fulfilled from a fixture, and every other
 * external host is aborted (see `e2e/support/api-mock.ts`). A spec that needs the live internet is
 * tagged `@live` and is excluded from the default run.
 */

const PORT = Number(process.env.E2E_PORT ?? 3100)
const BASE_URL = process.env.E2E_BASE_URL ?? `http://127.0.0.1:${PORT}`

export default defineConfig({
  testDir: "./e2e/specs",
  // Every assertion here is on a fully-rendered client surface, so give react-query's fetch +
  // hydration room without letting a genuinely-hung page burn the job.
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }], ["list"]] : [["list"]],

  // `@live` reaches the real internet (today: one DNS/reachability check on the Cognito Hosted-UI
  // host — the E9.58 outage class). Opt in with E2E_LIVE=1; never part of the hermetic gate.
  grepInvert: process.env.E2E_LIVE === "1" ? undefined : /@live/,

  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
      // ⚠️ `chromium` has no `testMatch`, so it runs EVERY file in `testDir` — including ones
      // written for the phone. `home-mobile.spec.ts` is the only spec here that is mobile-ONLY
      // (the two funnel specs below deliberately run on both), and running it on desktop is not
      // merely redundant: `Desktop Chrome` has no touch support, so `page.tap()` throws outright
      // ("The page does not support tap. Use hasTouch context option") — a hard failure that has
      // nothing to do with the page under test. Its layout assertions are equally meaningless at
      // 1280px, which is the quieter half of the same problem: they would pass on desktop while
      // proving nothing about the viewport they exist for.
      testIgnore: /home-mobile\.spec\.ts/,
    },
    // E9.58's second defect was mobile-only — the logged-out nav had no signup affordance on a
    // small screen because the whole block was `hidden sm:flex`. A desktop-only suite cannot see
    // that, so the funnel specs run on a phone viewport too.
    // ⭐ `expected-points-label` joins it for a DIFFERENT reason, and the distinction matters: its
    // tap test is VACUOUS on desktop. `InfoTip` opens on `pointerenter` when `pointerType ===
    // "mouse"`, so Chromium's `click()` opens the definition via HOVER before the click is even
    // dispatched — a Radix Tooltip, which can never be opened by a touch, would pass identically.
    // Only a touch-capable, hover-less viewport tells the two apart, and the phone reader is
    // exactly who the definition is for.
    {
      name: "mobile",
      use: { ...devices["Pixel 7"] },
    // ⭐ E9.46 joins for a THIRD reason. The home page is the highest-traffic surface in the
    // product and its two live cards are the densest layouts on it — the fantasy card alone packs
    // a four-column rank/ADP/games grid and a three-column format row. Those wrap, overflow or
    // truncate on a phone in ways `tsc` and `next build` cannot see, and this is the page a cold
    // visitor from a shared link lands on. `home-mobile.spec.ts` is scoped to what only a small
    // viewport can tell you; the rest of the home suite stays desktop-only rather than doubling.
      testMatch: /(signup-funnel|expected-points-label|home-mobile)\.spec\.ts/,
    },
  ],

  // `E2E_BASE_URL` means "something else is already serving" (a Vercel preview, a hand-started
  // `next start`), so don't try to launch one.
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: `npx next start -p ${PORT}`,
        url: BASE_URL,
        timeout: 120_000,
        reuseExistingServer: !process.env.CI,
        stdout: "pipe",
        stderr: "pipe",
      },
})
