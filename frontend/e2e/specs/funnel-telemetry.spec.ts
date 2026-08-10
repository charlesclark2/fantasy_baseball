import { expect, test, type Page } from "@playwright/test"
import { E2E_CHECKOUT_URL, captureAnalytics, mockApi, type CapturedEvent } from "../support/api-mock"
import { signIn } from "../support/session"

/**
 * G100-D0 — the funnel events, on the wire, from the real rendered app.
 *
 * ══ WHY THIS FILE EXISTS ═══════════════════════════════════════════════════════════════════════
 *
 * The founder dashboard reads six event NAMES and a handful of property names. Nothing in `tsc`,
 * `eslint` or `next build` can see any of that: an event that stopped firing, was renamed, or lost
 * a dimension compiles perfectly and ships a chart that reads ZERO. A zero on a conversion chart
 * does not look like a bug — it looks like a conversion collapse, which is the most expensive way
 * this whole story can fail.
 *
 * So every assertion here reads the INGEST REQUEST BODY. Not a stubbed `posthog.capture`, not a
 * spy: a test that stubbed the SDK would pass just as happily if PostHog were never initialised,
 * which is precisely the state this suite was in until G100-C1 armed a token in `e2e.env`.
 *
 * ⭐⭐ AND EVERY SPEC HERE DEPENDS ON `captureAnalytics` DEFEATING posthog-js's BOT FILTER. Two
 * clauses of it catch Playwright (`navigator.webdriver`, and "HeadlessChrome" in
 * `userAgentData.brands`), both have to go, and the failure is completely silent — the SDK
 * initialises, loads its remote config, and drops every event. Which means an assertion that an
 * event did NOT fire would pass on a totally healthy app. That is why the two negative specs below
 * each prove the wire is LIVE, in the same test, before concluding anything from an absence.
 *
 * ⛔ WHAT THIS FILE DOES NOT PROVE: that the events reach OUR PostHog project, with our token,
 * through the real `/ingest` rewrite. That is `docs/g100_d0_funnel.md` §7 — an operator walk of the
 * live funnel — and no hermetic suite can stand in for it.
 */

/** Give posthog's batcher room; it flushes on a timer, so a bare read races it. */
async function waitForEvent(events: CapturedEvent[], name: string): Promise<CapturedEvent[]> {
  await expect
    .poll(() => events.filter((e) => e.event === name).length, {
      message: `\`${name}\` never reached the ingest endpoint`,
      timeout: 10_000,
    })
    .toBeGreaterThan(0)
  return events.filter((e) => e.event === name)
}

/**
 * The window an ABSENCE assertion has to wait out.
 *
 * Long enough that "it had not flushed yet" is ruled out, which is what separates a real absence
 * from a race that happens to read empty. Matches the 3 s `free-league.spec.ts` uses for the same
 * job on the activation event.
 */
const ABSENCE_WINDOW_MS = 3_000

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 1. landing_view — the funnel's denominator
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("the home page fires landing_view under the name the dashboard reads", async ({ page }) => {
  await mockApi(page)
  const events = await captureAnalytics(page)
  await page.goto("/")

  const captured = await waitForEvent(events, "landing_view")
  expect(captured[0].properties.surface).toBe("home")
  // ⚠️ EXACTLY ONE per view. The once-per-mount ref is what stops a re-render multiplying a single
  // arrival; the dashboard's `count(DISTINCT person_id)` handles revisits, but it cannot undo an
  // event fired twice for one arrival if that ever became per-render.
  await page.waitForTimeout(ABSENCE_WINDOW_MS)
  expect(events.filter((e) => e.event === "landing_view")).toHaveLength(1)
})

test("each acquisition surface names itself", async ({ page }) => {
  // The `surface` dimension is how the dashboard answers "which free surface converts?", so a
  // surface that reports the wrong name is worse than one that reports nothing.
  for (const [path, surface] of [
    ["/fantasy/rankings", "fantasy_rankings"],
    ["/fantasy/projections", "fantasy_projections"],
  ] as const) {
    const context = await page.context().newPage()
    await mockApi(context)
    const events = await captureAnalytics(context)
    await context.goto(path)
    const captured = await waitForEvent(events, "landing_view")
    expect(captured[0].properties.surface, `${path} reported the wrong surface`).toBe(surface)
    await context.close()
  }
})

test("first-touch attribution survives an internal navigation", async ({ page }) => {
  // ⭐ THE LOAD-BEARING SPEC FOR THE WHOLE ATTRIBUTION DESIGN, and the one a plausible
  // implementation fails.
  //
  // Attribution is registered as a PostHog SUPER PROPERTY with `register_once`, so it rides on
  // every later event — including the activation and checkout events, which happen on surfaces
  // that have no idea where the visitor originally came from. The obvious alternative (derive the
  // dimensions per event, from the current URL and referrer) looks identical on the FIRST page and
  // is wrong on every page after it: the second view's referrer is OUR OWN HOST, so a campaign
  // visitor's second pageview would be attributed to `credencesports.com`, and their eventual
  // signup to `direct`.
  //
  // Landing with a utm and then clicking through is therefore the whole test.
  await mockApi(page)
  const events = await captureAnalytics(page)
  await page.goto("/?utm_source=e2e_reddit&utm_campaign=e2e_launch")

  const first = await waitForEvent(events, "landing_view")
  expect(first[0].properties.acquisition_source).toBe("e2e_reddit")
  expect(first[0].properties.campaign).toBe("e2e_launch")

  await page.goto("/fantasy/rankings")
  await expect
    .poll(() => events.filter((e) => e.event === "landing_view").length, { timeout: 10_000 })
    .toBeGreaterThan(1)

  const second = events.filter((e) => e.event === "landing_view").at(-1)!
  expect(second.properties.surface).toBe("fantasy_rankings")
  expect(
    second.properties.acquisition_source,
    "the second view lost first-touch attribution — a campaign visitor's signup would be " +
      "credited to `direct` or to our own host",
  ).toBe("e2e_reddit")
  expect(second.properties.campaign).toBe("e2e_launch")
})

test("an internal referrer is never recorded as an acquisition source", async ({ page }) => {
  // A visit with no utm and no external referrer is `direct` — and specifically NOT our own host,
  // which is the value a naive `document.referrer` read produces for every internal click and the
  // single easiest way to make an attribution breakdown useless.
  await mockApi(page)
  const events = await captureAnalytics(page)
  await page.goto("/")

  const captured = await waitForEvent(events, "landing_view")
  expect(captured[0].properties.acquisition_source).toBe("direct")
  expect(captured[0].properties.referrer).toBeNull()
})

test("/subscribe is NOT counted as a visitor", async ({ page }) => {
  // ⭐ THE NEGATIVE HALF OF THE DENOMINATOR, and it is a product decision rather than an oversight:
  // `/subscribe` is public but it is the CONVERSION surface, not an acquisition one. Counting
  // people who are already deep in the funnel as fresh visitors would depress every rate below and
  // manufacture a conversion problem that is not there.
  //
  // ⚠️ AND THE ABSENCE IS ONLY MEANINGFUL BECAUSE THE WIRE IS PROVEN LIVE IN THE SAME TEST. If the
  // bot filter were re-armed, or the token unset, this page would emit nothing at all and a bare
  // "landing_view did not fire" would pass against a completely broken harness. Clicking Subscribe
  // and watching `checkout_started` arrive is the proof that captures from THIS page reach the
  // ingest endpoint.
  await signIn(page, { groups: [] })
  await mockApi(page, { subscription: "none" })
  const events = await captureAnalytics(page)
  await page.route(E2E_CHECKOUT_URL, (route) => route.fulfill({ status: 204, body: "" }))

  await page.goto("/subscribe")
  await page.getByRole("button", { name: "Subscribe", exact: true }).click()
  await waitForEvent(events, "checkout_started")

  expect(
    events.filter((e) => e.event === "landing_view"),
    "/subscribe was counted at the top of the funnel",
  ).toHaveLength(0)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 2. checkout_started / subscription_started — the paid half
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("checkout_started leaves the page BEFORE the redirect to Stripe", async ({ page }) => {
  // ⭐ THE ORDERING IS THE POINT. `startCheckout` ends in `window.location.href = …`, so a capture
  // placed after the await would only ever run when checkout FAILED to start — a chart labelled
  // "checkout started" that is in fact a chart of backend errors, reading a healthy zero on a
  // perfect day. Answering the Stripe URL with a 204 keeps the document ours so the assertion can
  // run at all (an `abort()` strands the tab on about:blank).
  await signIn(page, { groups: [] })
  await mockApi(page, { subscription: "none" })
  const events = await captureAnalytics(page)
  await page.route(E2E_CHECKOUT_URL, (route) => route.fulfill({ status: 204, body: "" }))

  await page.goto("/subscribe")
  await page.getByRole("button", { name: "Subscribe", exact: true }).click()

  const captured = await waitForEvent(events, "checkout_started")
  expect(captured).toHaveLength(1)
  expect(captured[0].properties.surface).toBe("subscribe")
  // The price rides along, read from the SERVER (E9.59's rule: never a constant in this codebase),
  // so a pricing change is visible in the funnel rather than silently re-based.
  expect(captured[0].properties.unit_amount).toBe(1000)
  expect(captured[0].properties.tier).toBe("founding")
})

test("subscription_started fires once, only once access has actually landed", async ({ page }) => {
  await signIn(page, { groups: [] })
  await mockApi(page, { subscription: "active" })
  const events = await captureAnalytics(page)

  await page.goto("/subscribe/success")
  await expect(page.getByRole("heading", { name: /You're in/i })).toBeVisible()

  const captured = await waitForEvent(events, "subscription_started")
  // ⚠️ EXACTLY ONE, and the ref that guarantees it is doing real work rather than guarding a
  // theoretical double-invoke: `forceRefreshTokens` resolves null against the seeded session, and
  // on a live page a failing refresh sends the poll around again with `has_access` still true.
  // Without the ref that loop would emit a paid conversion every two seconds.
  await page.waitForTimeout(ABSENCE_WINDOW_MS)
  expect(events.filter((e) => e.event === "subscription_started")).toHaveLength(1)
  expect(captured[0].properties.free_paid_status).toBeDefined()
})

test("subscription_started does NOT fire while provisioning is still pending", async ({ page }) => {
  // ⭐ THE HALF THAT KEEPS THE NUMBER HONEST. Landing on /subscribe/success only means Stripe
  // redirected; the subscriber group is granted asynchronously by the webhook. An event fired on
  // mount would count a payment that never provisioned — and would fire again on every refresh of
  // this URL, which a confused user does exactly when provisioning is slow.
  //
  // ⚠️ NON-VACUITY. The success page emits no funnel event of its own while it is pending, so
  // there is nothing on THIS page to prove the wire with — and an absence assertion with no such
  // proof is exactly the shape that passes against a re-armed bot filter or an unset token.
  //
  // So the visit is preceded by a home-page view whose `landing_view` MUST arrive. That proves the
  // bot-filter defeat is in force and captures from this browser context reach the interceptor;
  // `addInitScript` applies to every document in the context, so the success page inherits it. A
  // capture from the success page would land in the same `events` array.
  await signIn(page, { groups: [] })
  await mockApi(page, { subscription: "none" })
  const events = await captureAnalytics(page)

  await page.goto("/")
  await waitForEvent(events, "landing_view")

  await page.goto("/subscribe/success")
  await expect(page.getByRole("heading", { name: /Confirming your membership/i })).toBeVisible()

  await page.waitForTimeout(ABSENCE_WINDOW_MS)
  expect(
    events.filter((e) => e.event === "subscription_started"),
    "a paid conversion was counted before the webhook granted access",
  ).toHaveLength(0)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 3. league_config_completed — the activation clause with NO production evidence
// ══════════════════════════════════════════════════════════════════════════════════════════════

/**
 * ⭐ THE HIGHEST-VALUE PAIR IN THIS FILE.
 *
 * `league_config_completed` is the second clause of G100-C1's activation definition and the only
 * one that has never been seen firing in production — it went out with the free-league build and
 * nothing has driven a genuinely-new account through a league CREATE since. Until these specs
 * existed there was no instrument anywhere, of any kind, that could tell "it fires" from "it has
 * silently never fired", and the dashboard would chart the difference as an activation rate of
 * zero.
 *
 * The CREATE/UPDATE split needs both halves and neither is redundant:
 *   · fires on a create → the funnel's third step is real.
 *   · silent on an update → one user tweaking a scoring weight cannot inflate the denominator that
 *     paid conversion is measured against. This is the failure an implementation naturally has,
 *     because "capture after a successful save" is the obvious place to put it.
 */
test("configuring a first league fires league_config_completed with its method", async ({
  page,
}) => {
  await signIn(page, { groups: [] })
  await mockApi(page, { leagues: "none" })
  const events = await captureAnalytics(page)

  await page.goto("/fantasy/league-settings")
  await page.getByRole("button", { name: "Save league", exact: true }).click()

  const captured = await waitForEvent(events, "league_config_completed")
  expect(captured).toHaveLength(1)
  // `method` is what separates the two doors into activation — the manual editor here, the platform
  // importer elsewhere. A funnel that saw only one door would read the other's users as never
  // having activated at all.
  expect(captured[0].properties.method).toBe("manual")
  expect(captured[0].properties.league_size).toBeDefined()
})

test("editing an EXISTING league counts no second activation", async ({ page }) => {
  // `leagues: "one"` → the editor loads the saved league, so its id is non-null and the save is a
  // PUT. Non-vacuous: the save is proven to have actually happened (the button reports "Saved")
  // before anything is concluded from the absence — otherwise a spec that failed to click at all
  // would pass.
  await signIn(page, { groups: [] })
  await mockApi(page, { leagues: "one" })
  const events = await captureAnalytics(page)

  await page.goto("/fantasy/league-settings")
  const save = page.getByRole("button", { name: "Save changes", exact: true })
  await expect(save).toBeVisible()
  await save.click()
  await expect(page.getByText(/saved/i).first()).toBeVisible()

  await page.waitForTimeout(ABSENCE_WINDOW_MS)
  expect(
    events.filter((e) => e.event === "league_config_completed"),
    "editing a league counted as a fresh activation — one user can now inflate the denominator " +
      "paid conversion is measured against, simply by saving twice",
  ).toHaveLength(0)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 4. The dimensions every step is broken down by
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("a logged-out visitor is `anonymous`, and carries a device class", async ({ page }) => {
  await mockApi(page)
  const events = await captureAnalytics(page)
  await page.goto("/")

  const captured = await waitForEvent(events, "landing_view")
  expect(captured[0].properties.free_paid_status).toBe("anonymous")
  expect(captured[0].properties.device).toBe("desktop")
})

/**
 * ⭐ THE ONE THAT PROTECTS THE HEADLINE NUMBER.
 *
 * `admin`, `beta_tester` and `fantasy_comp` all have full access and have paid nothing. If they
 * reported `paid`, the operator's own account and every beta tester would sit in the numerator of
 * ACTIVATION→paid — the metric the entire sprint is judged on. At launch scale that is not a
 * rounding error, it is most of the numerator, and the resulting conversion rate would be
 * flattering and fictional.
 *
 * One case per group, and each case's account is otherwise ordinary, so a group quietly dropping
 * out of the comped list fails on its own row rather than being masked by a sibling.
 */
for (const group of ["admin", "beta_tester", "fantasy_comp"] as const) {
  test(`a ${group} account reports \`comped\`, never \`paid\``, async ({ page }) => {
    await signIn(page, { groups: [group] })
    await mockApi(page)
    const events = await captureAnalytics(page)
    await page.goto("/")

    const captured = await waitForEvent(events, "landing_view")
    expect(
      captured[0].properties.free_paid_status,
      `${group} was counted as a paying conversion`,
    ).toBe("comped")
  })
}

test("a signed-in account with no entitlement is `free`; a subscriber is `paid`", async ({
  page,
}) => {
  for (const [groups, expected] of [
    [[], "free"],
    [["subscriber"], "paid"],
  ] as const) {
    const context: Page = await page.context().newPage()
    await signIn(context, { groups: [...groups] })
    await mockApi(context)
    const events = await captureAnalytics(context)
    await context.goto("/")

    const captured = await waitForEvent(events, "landing_view")
    expect(captured[0].properties.free_paid_status).toBe(expected)
    await context.close()
  }
})
