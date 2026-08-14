import { expect, test, type Page } from "@playwright/test"
import {
  E2E_YAHOO_AUTHORIZE_URL,
  FIXTURES,
  collectPageErrors,
  mockApi,
  type MockOptions,
} from "../support/api-mock"
import { signIn } from "../support/session"
import { expectNoNaN, expectNoPageErrors } from "../support/assertions"

/**
 * E9.64b — LEAGUE IMPORT, PATH 2 OF 2: YAHOO OAuth.
 *
 * ══ WHAT A HERMETIC RUN CAN AND CANNOT REACH, SAID UP FRONT ═══════════════════════════════════
 *
 * The one step this cannot drive is Yahoo's own consent screen, and faking a callback would
 * exercise our own stub — E9.64 declined the whole path on that basis. But the consent screen is
 * ONE step of six, and the other five are all in our app and were all untested:
 *
 *   1. the platform is OFFERED or refused, per its runtime `configured` state    ← in-app
 *   2. the connect click leaves for the AUTHORIZE URL THE SERVER SUPPLIED        ← in-app
 *   3. ~Yahoo's consent screen~                                                  ← not reachable
 *   4. the three `?yahoo=` return states the callback redirects back with        ← in-app
 *   5. list leagues → preview → review → save                                    ← in-app
 *   6. disconnect                                                                ← in-app
 *
 * Step 2 is the E9.58 shape exactly: that outage was an OAuth host which was internally consistent
 * in every file, type-checked, rendered a real button, fired a real click — and did not resolve. A
 * hermetic run cannot tell you whether Yahoo's host exists; it can prove the app sends the user to
 * the host THE SERVER NAMED rather than one the client assembled, which is the half that is ours.
 *
 * ⚠️⚠️ THE PAYLOAD IS NOT REAL, AND CANNOT BE TODAY — READ THIS BEFORE TRUSTING A GREEN RUN.
 * Yahoo gates all Fantasy API access behind a developer-application review that has not cleared
 * (`docs/nf_c0_yahoo_oauth_setup.md`: submitted 2026-08-01, still pending, SSM parameters
 * unwritten). There is no account anywhere — ours or anyone's — that can produce a real Yahoo
 * response, so the "≥2 independently-sourced real payloads" bar this story sets for ESPN is
 * **structurally unmeetable for Yahoo** and is NOT met here. What IS real is the response SHAPE:
 * the fixture is the output of the shipping `yahoo.import_league` adapter, so the page renders the
 * server's own structure rather than this session's guess at it — which is the half of NF-C0's
 * silent-outage class (a dropped response key; a 200 with a dead button) that a shape-guess fixture
 * could not catch. ⏭️ RE-GENERATE FROM A REAL LEAGUE THE DAY APPROVAL LANDS; that is the single
 * open item on this path, and it is recorded in `e2e/README.md` and in the builder's header.
 *
 * ⭐ THE DEFAULT MODE IS `unavailable`, BECAUSE THAT IS PRODUCTION. The captured platform catalog
 * says `configured: false`, so the state real users are in today is "coming soon" — and that state
 * has its own failure mode, tested first below.
 */

const REVIEW = /Review what we read/

async function openImport(page: Page, options: MockOptions = {}) {
  const errors = collectPageErrors(page)
  await signIn(page, { groups: [] })
  const mock = await mockApi(page, { entitlement: "free", leagues: "none", ...options })
  await page.goto(options.yahoo === "connected" ? "/fantasy/import?yahoo=connected" : "/fantasy/import")
  await page.getByRole("button", { name: /Yahoo/ }).first().click()
  return { errors, mock }
}

test.describe("Yahoo before it is approved — the state production is in", () => {
  test("the platform is listed, marked coming soon, and offers NO button to press", async ({
    page,
  }) => {
    // ⭐ THE FAILURE THIS GUARDS IS A DEAD BUTTON, and `list_platforms`' own docstring names it:
    // `available` (we built an adapter) and `configured` (it works right now) are reported
    // SEPARATELY so the UI can say "coming, pending registration" instead of hiding the option or
    // offering a control that 503s. Both wrong answers are plausible implementations — hiding it
    // reads to a Yahoo user as "this product does not support my platform", and offering it sends
    // them through a click that fails — so both are asserted against.
    const { errors } = await openImport(page, { yahoo: "unavailable" })

    await expect(
      page.getByRole("button", { name: /Yahoo/ }).first(),
      "Yahoo is hidden entirely, so a Yahoo user reads this as 'not supported'",
    ).toBeVisible()
    await expect(page.getByText("Coming soon", { exact: false }).first()).toBeVisible()
    await expect(
      // ⚠️ `exact`, because the platform CARD's own help text reads "Sign in with Yahoo to import a
      // league." — an unanchored match finds the card and would pass on the card being present.
      page.getByRole("button", { name: "Sign in with Yahoo", exact: true }),
      "a connect button is offered for a platform the server refuses with a 503",
    ).toHaveCount(0)

    // ⭐ AND IT MUST POINT AT THE FLOOR. The manual editor already works and produces the identical
    // config, so a user blocked here is inconvenienced rather than blocked — but only if they are
    // told. This is the copy that turns "come back later" into something to do now.
    // Matched on the SENTENCE, not the link text: the nav carries its own hidden
    // "My League Settings" entry, which resolves first and is not what this is about.
    await expect(
      page.getByText(/enter your Yahoo league by hand under My League Settings/),
    ).toBeVisible()

    expectNoPageErrors(errors)
  })
})

test.describe("connecting a Yahoo account", () => {
  test("⭐ the connect click leaves for the authorize URL the SERVER supplied", async ({ page }) => {
    // ⚠️ Answer 204, do NOT abort: a browser treats "No Content" on a top-level navigation as "stay
    // put", whereas an abort strands the tab on about:blank — whose origin is null, so the auth
    // context's localStorage read throws SecurityError and the failure has nothing to do with the
    // page under test. Same trap `signup-funnel.spec.ts` documents for the Cognito redirect.
    let authorizeUrl: string | null = null
    await page.route(/request_auth/, (route) => {
      authorizeUrl = route.request().url()
      return route.fulfill({ status: 204, body: "" })
    })

    const { errors } = await openImport(page, { yahoo: "disconnected" })
    await page.getByRole("button", { name: "Sign in with Yahoo", exact: true }).click()

    await expect
      .poll(() => authorizeUrl, {
        message: "pressing 'Sign in with Yahoo' never navigated anywhere — a dead button",
      })
      .not.toBeNull()
    // ⭐ VERBATIM, INCLUDING THE SIGNED `state`. That parameter is the ONLY thing binding the
    // returning grant to the account that started the flow (the callback is unauthenticated by
    // necessity — it is entered by a browser redirect and carries no bearer token), so a client that
    // rebuilt this URL from parts, or dropped a parameter it did not recognise, would produce a
    // consent round trip that either fails or grafts a Yahoo account onto the wrong Credence one.
    expect(authorizeUrl).toBe(E2E_YAHOO_AUTHORIZE_URL)

    expectNoPageErrors(errors)
  })

  // The callback always redirects the browser back with a status flag rather than answering JSON —
  // the user is mid-flow in a browser, so the outcome has to be legible on the page they land on.
  // All three are distinct facts and a single "something went wrong" banner for all of them would
  // be wrong twice: a user who CANCELLED has not hit a bug, and a user whose sign-in FAILED needs
  // to know nothing was saved before they try again.
  for (const [flag, expected] of [
    // The banner's own sentence — the platform card also renders a bare "connected" chip, so a
    // bare /Yahoo connected/ matches two elements and would pass on the chip alone.
    ["connected", /Yahoo connected\. Pick the league/],
    ["denied", /cancelled the Yahoo sign-in/],
    ["failed", /did not complete/],
  ] as const) {
    test(`the ?yahoo=${flag} return says what actually happened`, async ({ page }) => {
      const errors = collectPageErrors(page)
      await signIn(page, { groups: [] })
      await mockApi(page, {
        entitlement: "free",
        leagues: "none",
        yahoo: flag === "connected" ? "connected" : "disconnected",
      })
      await page.goto(`/fantasy/import?yahoo=${flag}`)

      await expect(
        page.getByText(expected),
        `returning from Yahoo with ?yahoo=${flag} reported nothing — the user cannot tell whether ` +
          "they are connected",
      ).toBeVisible()

      // A failure must not read as a success, in either direction.
      if (flag !== "connected") {
        await expect(page.getByText(/Yahoo connected\. Pick the league/)).toHaveCount(0)
        // ⭐ AND IT MUST SAY NOTHING WAS SAVED. A half-finished OAuth flow leaving a user unsure
        // whether we hold a grant is the state that makes people go looking for a revoke button.
        await expect(page.getByText(/[Nn]othing was (connected|saved)/)).toBeVisible()
      }
      expectNoPageErrors(errors)
    })
  }
})

test.describe("importing a connected Yahoo league", () => {
  async function reachReview(page: Page) {
    const opened = await openImport(page, { yahoo: "connected" })
    await page.getByRole("button", { name: /Load my Yahoo leagues/ }).click()
    const options = page.getByTestId("import-league-option")
    await expect(options.first(), "a connected account listed no Yahoo leagues").toBeVisible()
    await options.first().click()
    await expect(
      page.getByRole("heading", { name: REVIEW }),
      "picking a Yahoo league never reached the review screen",
    ).toBeVisible()
    return opened
  }

  test("the league list is the server's, and picking one reads its settings back", async ({
    page,
  }) => {
    const { errors } = await openImport(page, { yahoo: "connected" })
    await page.getByRole("button", { name: /Load my Yahoo leagues/ }).click()

    const listed = FIXTURES.importYahooLeagues().leagues as any[]
    expect(listed.length, "the Yahoo leagues fixture is empty; this case is unreachable").toBeGreaterThan(0)
    for (const league of listed) {
      await expect(page.getByText(league.name, { exact: false }).first()).toBeVisible()
    }

    await page.getByTestId("import-league-option").first().click()
    await expect(page.getByRole("heading", { name: REVIEW })).toBeVisible()

    const preview = FIXTURES.importYahooPreview() as any
    const review = page.locator("section").filter({ hasText: REVIEW }).first()
    await expect(review).toContainText(`${preview.config.n_teams}-team`)
    await expect(review).toContainText(preview.config.ppr.replace(/_/g, " "))
    await expect(review, "the review screen does not name Yahoo as the platform").toContainText("Yahoo")
    for (const slot of preview.config.roster.filter((s: any) => !s.bench)) {
      await expect(
        review.getByText(`${slot.count}× ${slot.name}`),
        `the ${slot.name} slot was not read back on the review screen`,
      ).toBeVisible()
    }

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("⭐ Yahoo's own identity pre-selects the user's team, and only theirs", async ({ page }) => {
    // ⭐ THE ONE THING YAHOO CAN DO THAT NO OTHER PLATFORM CAN. OAuth means the response carries
    // `is_current_login`, so the preview knows which team is the caller's and `applyPreview`
    // pre-selects it — which is what lets My Teams score a roster without the user picking. Sleeper
    // and ESPN cannot, and their branch of this screen asks instead (asserted in the ESPN spec).
    //
    // ⚠️ Getting this WRONG is not a crash: pre-selecting the wrong team links a stranger's roster
    // to the user's league and renders perfectly. So "exactly one, and it is the flagged one" is the
    // assertion, not "something is selected".
    const { errors } = await reachReview(page)

    const preview = FIXTURES.importYahooPreview() as any
    const owned = preview.teams.filter((t: any) => t.is_owner)
    expect(owned, "the Yahoo fixture flags no owner; this case is unreachable").toHaveLength(1)

    const marked = page.getByRole("button", { name: "✓ Mine" })
    await expect(marked, "Yahoo told us which team is the user's and the screen did not mark it").toHaveCount(1)
    // The marked one is the FLAGGED one, not merely the first row.
    const row = page.locator("div").filter({ hasText: owned[0].name }).last()
    await expect(row.getByRole("button", { name: "✓ Mine" })).toHaveCount(1)
    await expect(
      page.getByText(/We've marked which one is yours/),
      "the screen marked a team without telling the user it had guessed",
    ).toBeVisible()

    expectNoPageErrors(errors)
  })

  test("⭐ Yahoo's required attribution is rendered wherever their data is", async ({ page }) => {
    // 🚩 A CONTRACTUAL REQUIREMENT, not a nicety: Yahoo's API terms require attribution wherever
    // their data is shown, and it renders only on a Yahoo preview. Nothing else in the repo can see
    // it — it is a string in a branch no test had ever entered — and losing it is a compliance
    // failure that looks, from every other instrument, like a clean page.
    const { errors } = await reachReview(page)

    const link = page.getByRole("link", { name: /Fantasy data provided by Yahoo/ })
    await expect(link, "the Yahoo attribution is missing from a screen showing Yahoo data").toBeVisible()
    await expect(link).toHaveAttribute("href", /yahoo\.com/)

    expectNoPageErrors(errors)
  })

  test("the scoring we can apply is reported as applied, and the rest is named", async ({ page }) => {
    const { errors } = await reachReview(page)

    const applied = page.getByTestId("coverage-applied")
    await expect(applied).toBeVisible()
    // Yahoo maps its stats by ID rather than by name — deliberately, because id 6 "Interceptions"
    // (thrown, negative) and id 33 "Interception" (made by a defense, positive) are different stats
    // a name-matching importer conflates, paying quarterbacks for defensive picks. Both must land
    // applied, under their canonical keys, or that whole distinction has been lost downstream.
    for (const key of ["pass_yds", "pass_int", "def_int", "rec"]) {
      await expect(
        applied.getByText(key, { exact: true }),
        `${key} is not reported as APPLIED for a Yahoo import`,
      ).toBeVisible()
    }

    // And a term we genuinely cannot project is named rather than dropped.
    const preview = FIXTURES.importYahooPreview() as any
    for (const key of preview.unmapped_scoring_keys) {
      await expect(
        page.getByTestId("coverage-captured").getByText(key, { exact: false }),
        `the captured rule ${key} is not reported anywhere on the review`,
      ).toBeVisible()
    }

    expectNoPageErrors(errors)
  })

  test("saving a Yahoo import links the pre-selected team", async ({ page }) => {
    // The other half of the pre-selection: it has to survive into the SAVE. A screen that marked the
    // team and then saved `source_team_key: null` would render identically and leave My Teams empty.
    const { errors } = await reachReview(page)

    await page.getByRole("button", { name: /Save this league/ }).click()
    await expect(page.getByText(/League saved/)).toBeVisible()
    await expect(
      page.getByText(/Your team is linked/),
      "a league saved with a pre-selected team reported no roster linked",
    ).toBeVisible()

    expectNoPageErrors(errors)
  })

  test("disconnecting says exactly what it did, and does not overstate it", async ({ page }) => {
    // ⚠️ WE CANNOT REVOKE A YAHOO GRANT — only Yahoo can. Deleting our copy and calling it
    // "revoked" would be the kind of quiet overstatement this product does not make, and a user who
    // believed it would leave a live grant standing at Yahoo. So the copy has to name both halves.
    const { errors } = await openImport(page, { yahoo: "connected" })

    await expect(page.getByText(/Disconnecting deletes our copy/)).toBeVisible()
    const yahooAccount = page.getByRole("link", { name: /your Yahoo account settings/ })
    await expect(
      yahooAccount,
      "the screen does not point at the only place the grant can actually be revoked",
    ).toBeVisible()
    await expect(yahooAccount).toHaveAttribute("href", /login\.yahoo\.com/)

    await page.getByRole("button", { name: /Disconnect/ }).click()
    // The list must be cleared — leaving the previous account's leagues on screen after a disconnect
    // reads as though the grant is still live.
    await expect(page.getByTestId("import-league-option")).toHaveCount(0)

    expectNoPageErrors(errors)
  })
})
