import { expect, test, type Page } from "@playwright/test"
import {
  E2E_IMPORT_UNMAPPED_KEY,
  E2E_IMPORT_WARNING,
  FIXTURES,
  collectPageErrors,
  mockApi,
} from "../support/api-mock"
import { signIn } from "../support/session"
import { expectNoNaN, expectNoPageErrors } from "../support/assertions"

/**
 * E9.64 — LEAGUE IMPORT: the review queue, and saving.
 *
 * ══ WHAT WAS ALREADY COVERED, AND WHERE IT STOPPED ════════════════════════════════════════════
 *
 * `free-league.spec.ts` drives the importer as far as the LEAGUE LIST, because that is where
 * G100-C1's quota boundary is drawn. Step 2 — "Review what we read", the screen between picking a
 * league and owning it — was never opened by anything, and the api-mock deliberately had no
 * `preview` endpoint. That is the single highest-consequence screen in the fantasy product:
 *
 *   ⭐ IT IS THE ONLY PLACE A USER CAN LEARN THAT WE DID NOT UNDERSTAND THEIR LEAGUE. The component's
 *   own comment says it: "an import that quietly loses a rule is the failure this whole surface
 *   guards." A league whose scoring we silently dropped produces a board that is confidently wrong
 *   all season, on the user's own settings, with nothing anywhere reporting a problem.
 *
 * So the assertions here are about DISCLOSURE far more than about mechanics: the settings we read
 * are shown, the rules we could not represent are shown VERBATIM, and — the failure mode CLAUDE.md
 * names outright — a coverage panel that cannot check must SAY it could not, never fall through to
 * an optimistic "everything applies".
 *
 * ⚠️ Import is a WRITE path, so the real gate is the server (`/fantasy/import/*`, `/fantasy/leagues`)
 * and is asserted against the real ASGI app. Nothing here proves authorization.
 */

/** Get a signed-in free account to the review screen for the un-saved league in the fixture. */
async function openReview(page: Page, options: { failProjections?: boolean } = {}) {
  const errors = collectPageErrors(page)
  await signIn(page, { groups: [] })
  const mock = await mockApi(page, {
    entitlement: "free",
    // No league saved ⇒ nothing is quota-locked, so the whole flow is open. The locked variant is
    // `free-league.spec.ts`'s subject and is deliberately not re-tested here.
    leagues: "none",
    fail: options.failProjections ? ["/fantasy/nfl/projections"] : undefined,
  })
  await page.goto("/fantasy/import")

  await page.getByPlaceholder("Paste your Sleeper league ID").fill("e2e-tester")
  await page.getByRole("button", { name: "Import", exact: true }).click()

  // Pick the first league the platform offered. The list itself is `free-league.spec.ts`'s subject;
  // here it is just the door to step 2.
  const options_ = page.getByTestId("import-league-option")
  await expect(options_.first()).toBeVisible()
  await options_.first().click()

  await expect(
    page.getByRole("heading", { name: /Review what we read/ }),
    "picking a league never reached the review screen",
  ).toBeVisible()
  return { errors, mock }
}

test.describe("the review screen reports what we actually read", () => {
  test("the league's own settings are read back before anything is saved", async ({ page }) => {
    const { errors } = await openReview(page)
    const league = FIXTURES.myTeams().leagues[0] as any

    // Read back from the payload, not hardcoded: the point is that the screen echoes the SERVER's
    // reading of the league, which is the only thing the user can check it against.
    const review = page.locator("section").filter({ hasText: "Review what we read" }).first()
    await expect(review).toContainText(`${league.n_teams}-team`)
    await expect(review).toContainText(/half/i)
    await expect(review, "the superflex slot the league actually has is not read back").toContainText(
      /superflex/i,
    )

    // The starting lineup, which is what makes "12-team half-PPR" concrete. A roster shape read
    // wrongly is the difference between a useful board and a wrong one.
    const starters = (league.roster as any[]).filter((s) => !s.bench)
    for (const slot of starters) {
      await expect(
        review.getByText(`${slot.count}× ${slot.name}`),
        `the ${slot.name} slot was not read back on the review screen`,
      ).toBeVisible()
    }

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("⭐ a rule we could not represent is shown, word for word, before saving", async ({ page }) => {
    // ⭐⭐ THE ASSERTION THIS FILE EXISTS FOR. A silently-dropped scoring rule is not a crash and not
    // a blank — it is a board that is wrong all season on the user's own settings, and this screen
    // is the only place it is ever mentioned. The warning text is server-supplied and rendered
    // verbatim, so it is checked verbatim: a component that summarised, truncated or "tidied" these
    // into a count would pass any "a warning is visible" assertion and lose the actual rule.
    const { errors } = await openReview(page)

    await expect(page.getByText(/What we could not read exactly/)).toBeVisible()
    await expect(
      page.getByText(E2E_IMPORT_WARNING, { exact: false }),
      "the server said it could not represent a rule and the review screen did not pass it on",
    ).toBeVisible()

    // The captured-but-unprojected key is accounted for too, rather than silently discarded.
    await expect(
      page.getByText(E2E_IMPORT_UNMAPPED_KEY, { exact: false }),
      "a scoring key we store but do not project is not reported anywhere on the review",
    ).toBeVisible()

    expectNoPageErrors(errors)
  })

  test("⛔ a coverage check that could not run says so, and never claims everything applies", async ({
    page,
  }) => {
    // ⭐ THE HONEST-EMPTY-STATE CLASS, and the one CLAUDE.md names directly: a coverage panel that
    // treats a MISSING read as "everything applies" makes a FALSE claim about the user's league on
    // any upstream outage. The resolver reads an absent column set as "we have everything", so the
    // optimistic render is the NATURAL one to write — which is exactly why it needs a test.
    //
    // `fail` is what makes this reachable: `transform` rewrites a body that was successfully served
    // and structurally cannot express the read itself failing.
    const { errors } = await openReview(page, { failProjections: true })

    await expect(
      page.getByText(/We could not check your scoring coverage/),
      "a failed projections read rendered no coverage caveat — the panel is either silently absent " +
        "or optimistically claiming every rule applies",
    ).toBeVisible()
    await expect(
      page.getByText(/settings above are correct and safe to save/),
      "the reader is told the check failed but not whether they can proceed",
    ).toBeVisible()

    // ⭐ AND THE FAILURE MUST NOT TAKE THE FUNNEL WITH IT — the E9.59 lesson (a display outage
    // becoming a funnel outage). The settings are still saveable; only the breakdown is missing.
    await expect(page.getByRole("button", { name: /Save this league/ })).toBeEnabled()

    expectNoPageErrors(errors)
  })

  test("the coverage breakdown renders when the projections DO load", async ({ page }) => {
    // The other side, so "always say we could not check" cannot satisfy the test above.
    const { errors } = await openReview(page)

    await expect(page.getByText(/We could not check your scoring coverage/)).toHaveCount(0)
    // The three verdicts NF-C0d reports. `captured` is the one that matters — it is where a rule we
    // store but do not project is counted.
    for (const verdict of ["applied", "derived", "captured"]) {
      await expect(
        page.getByText(new RegExp(`${verdict} · \\d+`, "i")),
        `the coverage panel does not report "${verdict}" terms`,
      ).toBeVisible()
    }
    expectNoPageErrors(errors)
  })
})

test.describe("saving an imported league", () => {
  test("saving reports that it happened, and says whether a team was linked", async ({ page }) => {
    // ⭐ E8.6's lesson, on the other create path: a save that reports nothing is indistinguishable
    // from a save that silently did not happen — which is exactly how a deploy-skew dropped field
    // presented (a 200, an optimistic value, and a phantom revert).
    const { errors } = await openReview(page)

    await page.getByRole("button", { name: /Save this league/ }).click()

    await expect(
      page.getByText(/League saved/),
      "the save produced no confirmation — the user cannot tell it happened",
    ).toBeVisible()
    // No team was picked, so the message must say so rather than implying a roster is linked. The
    // two states send the user to different next steps.
    await expect(
      page.getByText(/No team linked yet/),
      "a league saved without a team claimed the roster was linked",
    ).toBeVisible()

    expectNoPageErrors(errors)
  })
})
