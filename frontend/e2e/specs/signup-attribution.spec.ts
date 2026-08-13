import { expect, test, type Page } from "@playwright/test"
import { captureAnalytics, mockApi, type CapturedEvent, type MockOptions } from "../support/api-mock"
import { fakeOAuthTokens } from "../support/session"

/**
 * G100-D0-R1 — `user_signup_completed` counts ACCOUNTS, not button clicks.
 *
 * ══ WHY THIS FILE EXISTS ═══════════════════════════════════════════════════════════════════════
 *
 * The event used to key on which affordance was pressed, stashed across the sign-in round trip.
 * But every self-serve door auto-provisions an account, so that rule was wrong twice over: a
 * first-timer arriving at the SIGN IN door got a real new account and emitted nothing (and R1's
 * ordered funnel then discarded them entirely — neither a signup nor a drop-off), while a
 * returning user clicking SIGN UP emitted a signup that never happened. In production's first
 * 48h, all 16 auth events used the /login door.
 *
 * ⭐ THE CONDITION IS NOW SERVER-SIDE, WHICH IS EXACTLY WHY IT NEEDS A BROWSER TEST. A source
 * guard can prove the emit sits under `acceptance.created`; it cannot prove that branch is
 * REACHABLE — that the response parses, that the promise resolves before the page navigates away,
 * or that posthog's batcher survives that navigation. All three are runtime facts, each one fails
 * silently, and all three look identical from outside: a zero on step 2 of the funnel.
 *
 * ══ WHY THE EMAIL DOOR RATHER THAN GOOGLE ═════════════════════════════════════════════════════
 *
 * ⛔ THE GOOGLE ROUND TRIP CANNOT BE DRIVEN HERMETICALLY, and it is worth writing down so nobody
 * spends an afternoon rediscovering it: `completeGoogleSignIn` POSTs to the Cognito Hosted-UI
 * `/oauth2/token` endpoint, and `next.config.mjs` pins `connect-src` to the PRODUCTION Hosted-UI
 * host. The E2E build is compiled with a deliberately fake one, so the browser refuses the request
 * — "Failed to fetch (…e2etestpool…)" — BEFORE Playwright can route it (the same wall that forces
 * `NEXT_PUBLIC_API_URL` to be same-origin; see `e2e/e2e.env`).
 *
 * The email-OTP door has no such problem: both its legs go through OUR API, which the harness
 * already intercepts. And it is not a lesser subject — it is a REAL self-serve door that
 * auto-provisions exactly like Google, both doors hand off to the SAME `completeSignIn`, and the
 * decision under test lives entirely inside that shared module (which is why `lib/post-signin.ts`
 * exists at all). The Google page's delegation to it is pinned separately, in
 * `betting_ml/tests/test_g100_d0_r1_signup_authoritative.py` and `test_g100_c0_email_otp.py`.
 *
 * ⭐⭐ AND LIKE EVERY SPEC IN `funnel-telemetry.spec.ts`, ALL OF THIS DEPENDS ON `captureAnalytics`
 * DEFEATING posthog-js's BOT FILTER (`navigator.webdriver` AND "HeadlessChrome" in
 * `userAgentData.brands` — both, silently). That matters most for the three NEGATIVE specs here:
 * an assertion that an event did NOT fire passes perfectly against a harness that captures
 * nothing. So each negative proves the wire is LIVE in the same test by first requiring
 * `user_signed_in`, which the same function emits unconditionally milliseconds earlier.
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

/** Long enough that "it had not flushed yet" is ruled out — matches the sibling specs. */
const ABSENCE_WINDOW_MS = 3_000

const OTP_EMAIL = "new-user@example.com"

/**
 * Walk a real self-serve sign-in from one of the two doors, and land signed in.
 *
 * `door` is the whole independent variable: `/signup` declares `intent: "signup"`, `/login`
 * declares `intent: "signin"`. Pre-R1 that alone decided whether the signup event fired; it must
 * now decide nothing except during a backend deploy skew.
 */
async function walkEmailDoor(
  page: Page,
  door: "/login" | "/signup",
  options: MockOptions,
): Promise<CapturedEvent[]> {
  await mockApi(page, options)
  const events = await captureAnalytics(page)

  // The two OTP legs. Answered here rather than in `api-mock` because the tokens have to be
  // structurally real — `verifyEmailOtp` hands them to `hydrateSessionFromTokens`, which decodes
  // the id token and writes the trio into the Cognito SDK's storage layout.
  await page.route("**/auth/email-otp/start", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ next: "otp", masked_email: "n***@example.com", session: "e2e-session" }),
    }),
  )
  await page.route("**/auth/email-otp/verify", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(fakeOAuthTokens({ email: OTP_EMAIL })),
    }),
  )

  await page.goto(door)
  if (door === "/login") {
    // /login opens on the password form; the email door is one click in.
    await page.getByRole("button", { name: "Email me a sign-in code instead" }).click()
  }

  await page.getByLabel("Email").fill(OTP_EMAIL)
  await page.getByRole("button", { name: "Email me a sign-in code" }).click()

  await page.getByLabel("Sign-in code").fill("123456")
  await page.getByRole("button", { name: "Verify & continue" }).click()
  return events
}

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 1. The under-count this story exists to fix
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("a NEW account arriving through the SIGN IN door is counted as a signup", async ({ page }) => {
  // ⭐ THE HEADLINE SPEC. Pre-R1 this produced `user_signin_started` / `user_signed_in` and
  // nothing else, and the ordered funnel discarded the person outright. It is not an edge case:
  // every one of production's first 16 auth events took the /login door.
  const events = await walkEmailDoor(page, "/login", { termsAcceptance: "created" })

  const captured = await waitForEvent(events, "user_signup_completed")
  expect(captured, "the /login door counted more than one signup for one account").toHaveLength(1)
  // "server" means the Lambda answered — the authoritative reading. It is what makes a funnel
  // read during a backend deploy diagnosable rather than merely suspicious.
  expect(captured[0].properties.signal).toBe("server")
  // A signup event carrying a SIGNIN intent is the entire finding, and no client-side rule can
  // produce it.
  expect(captured[0].properties.intent).toBe("signin")
  expect(captured[0].properties.method).toBe("email_otp")
  expect(captured[0].properties.surface).toBe("login")
})

test("a new account through the SIGN UP door is still counted, exactly once", async ({ page }) => {
  // The pre-existing behaviour must survive the re-keying — a fix that swapped one blind door for
  // the other would be no fix. ALSO the double-count guard: here the server answer and the client
  // intent BOTH say "signup", so an implementation that emitted on either would emit twice, and a
  // person-level funnel would hide that until the day the two disagreed.
  const events = await walkEmailDoor(page, "/signup", { termsAcceptance: "created" })

  const captured = await waitForEvent(events, "user_signup_completed")
  await page.waitForTimeout(ABSENCE_WINDOW_MS)
  expect(
    events.filter((e) => e.event === "user_signup_completed"),
    "one signup produced two events — the server answer and the client intent are both firing",
  ).toHaveLength(1)
  expect(captured[0].properties.signal).toBe("server")
  expect(captured[0].properties.surface).toBe("signup")
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 2. The FALSE POSITIVE — the other direction, and just as wrong
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("a RETURNING user who clicks Sign Up is not counted as a signup", async ({ page }) => {
  // ⭐ Fixing one direction and not the other leaves the funnel wrong: this person inflated R1's
  // numerator with a signup that never happened. The server says `created: false`, and that must
  // beat the button — which is the one place a "helpful" fallback would quietly restore the bug.
  //
  // ⚠️ NON-VACUITY: the absence below means nothing unless captures from this page reach the
  // interceptor at all. `user_signed_in` is emitted by the SAME function, unconditionally, moments
  // earlier — requiring it first is what separates "the app correctly stayed silent" from "the bot
  // filter is back and this suite is measuring nothing".
  const events = await walkEmailDoor(page, "/signup", { termsAcceptance: "existing" })

  const signedIn = await waitForEvent(events, "user_signed_in")
  expect(signedIn[0].properties.intent).toBe("signup")

  await page.waitForTimeout(ABSENCE_WINDOW_MS)
  expect(
    events.filter((e) => e.event === "user_signup_completed"),
    "a returning user who clicked Sign Up was counted as a new signup — the client's intent is " +
      "overriding the server's authoritative created:false",
  ).toHaveLength(0)
})

test("a returning user at the SIGN IN door is not counted either", async ({ page }) => {
  // The ordinary steady state — every sign-in after the first. It must stay silent, or R1's
  // numerator becomes a count of sign-ins and the conversion rate is meaningless.
  const events = await walkEmailDoor(page, "/login", { termsAcceptance: "existing" })

  await waitForEvent(events, "user_signed_in")
  await page.waitForTimeout(ABSENCE_WINDOW_MS)
  expect(
    events.filter((e) => e.event === "user_signup_completed"),
    "an ordinary returning sign-in was counted as a signup",
  ).toHaveLength(0)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 3. The deploy skew — the API Lambda ships only via deploy.sh
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("an un-deployed backend degrades to the OLD rule, labelled, rather than to zero", async ({
  page,
}) => {
  // ⭐ THE STATE THAT IS GUARANTEED TO HAPPEN AT LEAST ONCE. `frontend/` auto-deploys on merge to
  // main; the API Lambda ships only via deploy.sh. In that window the old endpoint answers 204
  // with no body, so `created` is ABSENT — which must NOT read as `created: false`, because that
  // takes step 2 of the funnel to a flat zero, and a zero on a conversion chart reads as a
  // conversion collapse rather than as a missing deploy. Falling back to the pre-R1 intent rule
  // holds the window at the OLD, already-understood under-count instead.
  const events = await walkEmailDoor(page, "/signup", { termsAcceptance: "skew" })

  const captured = await waitForEvent(events, "user_signup_completed")
  expect(captured).toHaveLength(1)
  expect(
    captured[0].properties.signal,
    "the skew-window event is indistinguishable from an authoritative one, so a funnel read " +
      "during a deploy cannot be told apart from one taken after it",
  ).toBe("intent_fallback")
})

test("the skew fallback still respects the door it fell back to", async ({ page }) => {
  // The fallback is the OLD rule, not a free pass: with no server answer and a SIGN IN intent
  // there is no evidence an account was created, so it stays silent. This reproduces the pre-R1
  // under-count deliberately — it is what "degrades to the old behaviour" has to mean.
  const events = await walkEmailDoor(page, "/login", { termsAcceptance: "skew" })

  await waitForEvent(events, "user_signed_in")
  await page.waitForTimeout(ABSENCE_WINDOW_MS)
  expect(
    events.filter((e) => e.event === "user_signup_completed"),
    "the skew fallback invented a signup from a sign-in intent",
  ).toHaveLength(0)
})
