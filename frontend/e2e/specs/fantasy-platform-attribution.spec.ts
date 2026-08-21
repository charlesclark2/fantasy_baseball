import { expect, test, type Page } from "@playwright/test"
import {
  E2E_DRAFTED_LEAGUE,
  E2E_YAHOO_LEAGUE,
  collectPageErrors,
  mockApi,
  type MockOptions,
} from "../support/api-mock"
import { signIn } from "../support/session"
import { expectNoPageErrors } from "../support/assertions"

/**
 * NF-C0-Yahoo-ENABLE (Half A) — 🚩 THE PLATFORM ATTRIBUTION, ON EVERY SURFACE THAT SHOWS THE DATA.
 *
 * ══ WHY THIS IS A BROWSER TEST AND NOT A SOURCE GUARD ═════════════════════════════════════════
 *
 * Yahoo's API terms (Cover / §5) require "Fantasy data provided by Yahoo Fantasy", hyperlinked back
 * to Yahoo Fantasy, wherever their data is shown. The NF-C0-Yahoo spike measured us rendering it in
 * exactly ONE place — the import PREVIEW, before the league is even saved — while every surface
 * showing the data AFTER the save showed none.
 *
 * A grep for the string would have passed the whole time. It was present in the codebase; it simply
 * never reached seven of the eight screens that owe it. That is the NF-C4 lesson verbatim — a
 * frontend guard that reads SOURCE tests that somebody typed a string, not that a page renders it —
 * so every assertion here is against RENDERED OUTPUT on a real route.
 *
 * ══ WHY EVERY CASE IS RUN TWICE ═══════════════════════════════════════════════════════════════
 *
 * ⭐ THE `drafted` MODE IS THE OTHER HALF OF EVERY ASSERTION, and without it this file would be
 * vacuous in the most convincing way available. `yahooImported` and `drafted` are the SAME league
 * differing in `source_platform` alone, so:
 *   · a component that never renders the credit fails the Yahoo case;
 *   · a component that renders it unconditionally fails the Sleeper case — and that is a real
 *     compliance problem of its own, not a cosmetic one: crediting Yahoo for data Yahoo did not
 *     supply is a false statement about a third party on our own product.
 * One-sided, a stub returning the link on every page would pass every test in this file.
 *
 * ══ AND IT MUST BE IN THE FOOTER ══════════════════════════════════════════════════════════════
 *
 * The Cover Page is specific about placement — "attribution must appear IN THE FOOTER OF EACH PAGE
 * where Yahoo Fantasy Information is displayed" — and Half A put it at the end of each surface's
 * MAIN CONTENT, above the site footer, because the spike memo's paraphrase did not carry the word
 * "footer" and the clause text was not available. So every case below asserts the credit inside the
 * page's `<footer>` element, not merely somewhere on the page: a credit that drifts back out of the
 * footer would look identical to a reader and would not satisfy the clause.
 *
 * ⛔ WHAT THIS FILE DOES NOT PROVE. That the string and URL are the ones Yahoo's terms actually
 * name, and that the SERVER agrees with the client about them. Those are asserted against the
 * shipping Python constants in `betting_ml/tests/test_nf_c0_yahoo_halfa_compliance.py`.
 */

/** Every post-save surface that can put an imported league's data on screen, and how to get there.
 *
 *  ⚠️ THIS LIST IS THE DELIVERABLE, not a convenience. The compliance gap was never "the component
 *  is wrong" — it was "six screens nobody enumerated". Adding a surface that renders a saved league
 *  means adding a row here; a surface missing from this table is a surface nobody is checking. */
const SURFACES: { name: string; open: (page: Page) => Promise<void> }[] = [
  {
    name: "My League",
    open: async (page) => {
      // No `?league=` id: the surface defaults to the caller's only league, which is the one the
      // active mode serves. Naming an id here would pin this to the Yahoo mode and make the
      // Sleeper case resolve nothing.
      await page.goto("/fantasy/my-league")
      // The BOARD, not just the heading: the credit sits below it, and waiting on a header that
      // renders before the league resolves would let the assertion run against a half-built page.
      await expect(page.getByTestId("my-league-board")).toBeVisible()
    },
  },
  {
    name: "My Teams",
    open: async (page) => {
      await page.goto("/fantasy/my-teams")
      await expect(page.getByRole("heading", { name: "My Teams" })).toBeVisible()
    },
  },
  {
    name: "Roster report",
    open: async (page) => {
      await page.goto("/fantasy/roster-report")
      await expect(
        page.getByRole("heading", { name: "Your roster, read against your league" }),
      ).toBeVisible()
    },
  },
  {
    name: "League board",
    open: async (page) => {
      await page.goto("/fantasy/league-board")
      await selectSavedLeague(page)
    },
  },
  {
    name: "Draft optimizer",
    open: async (page) => {
      await page.goto("/fantasy/draft")
      await selectSavedLeague(page)
    },
  },
  {
    name: "Auction optimizer",
    open: async (page) => {
      await page.goto("/fantasy/auction")
      await selectSavedLeague(page)
    },
  },
  {
    name: "League settings",
    open: async (page) => {
      await page.goto("/fantasy/league-settings")
      // The editor loads the caller's first saved league on its own — no picking required, which is
      // itself the point: a user lands on their imported league without touching anything.
      await expect(page.getByRole("heading", { name: "League settings" })).toBeVisible()
    },
  },
]

/**
 * Choose the caller's ONE saved league in the format picker.
 *
 * ⚠️ Click the trigger, then the option. These are Radix `Picker`s, not native `<select>`s (the
 * repo's mobile-form-control guard requires it), and Playwright's `selectOption` silently does
 * NOTHING on a Radix trigger — the surface would stay on its default preset and the assertion would
 * be about a board the saved league never touched.
 */
async function selectSavedLeague(page: Page) {
  const picker = page.getByLabel("Scoring format")
  await expect(picker).toBeVisible()
  await picker.click()
  await page.getByRole("option", { name: new RegExp(LEAGUE_NAME) }).click()
  // The picker must actually be ON the league now — a click that missed leaves the surface on its
  // default preset, where a MISSING credit is the correct answer and the Yahoo case would fail for
  // a reason that has nothing to do with attribution.
  await expect(picker).toContainText(LEAGUE_NAME)
}

/**
 * The league name currently on screen.
 *
 * ⚠️ MUTATED BY `open` rather than passed down, because the SURFACES table is built once at module
 * scope and both modes run through it. `yahooImported` and `drafted` are the same league under
 * different names, and a picker driven with the wrong one silently leaves the surface on a preset —
 * which renders no credit, i.e. the Sleeper case would PASS for the wrong reason.
 */
let LEAGUE_NAME: string = E2E_YAHOO_LEAGUE.name

async function open(page: Page, surface: (typeof SURFACES)[number], options: MockOptions = {}) {
  const errors = collectPageErrors(page)
  LEAGUE_NAME = options.leagues === "drafted" ? E2E_DRAFTED_LEAGUE.name : E2E_YAHOO_LEAGUE.name
  await signIn(page, { groups: ["subscriber"] })
  const mock = await mockApi(page, { entitlement: "entitled", leagues: "yahooImported", ...options })
  await surface.open(page)
  return { errors, mock }
}

/** ⚠️ SCOPED TO `<footer>` DELIBERATELY. `getByTestId` alone would pass just as happily with the
 *  credit back in the page body, which is where it used to be and is what the clause rules out. */
const attribution = (page: Page) => page.locator("footer").getByTestId("platform-attribution")

for (const surface of SURFACES) {
  test.describe(surface.name, () => {
    test(`renders Yahoo's required attribution when the league came from Yahoo`, async ({ page }) => {
      const { errors } = await open(page, surface)

      const line = attribution(page).first()
      await expect(
        line,
        `${surface.name} shows a Yahoo-imported league with no attribution — a compliance failure ` +
          `that looks, from every other instrument, like a clean page`,
      ).toBeVisible()

      // The LINK is the requirement, not the sentence: the terms ask for a credit that goes back to
      // Yahoo Fantasy. Plain text carrying the same words would satisfy a naive text assertion.
      const link = line.getByRole("link", { name: /Fantasy data provided by Yahoo Fantasy/ })
      await expect(link).toBeVisible()
      await expect(link).toHaveAttribute("href", /fantasysports\.yahoo\.com/)

      expectNoPageErrors(errors)
    })

    test(`renders NO Yahoo attribution when the same league came from Sleeper`, async ({ page }) => {
      // ⭐ The other half. `drafted` is `yahooImported` minus one field, so this failing means the
      // credit is not keyed on provenance — either it is hardcoded on the page, or the component is
      // rendering for every platform. Both are wrong, and only this direction can see them.
      const { errors } = await open(page, surface, { leagues: "drafted" })

      await expect(
        page.getByTestId("platform-attribution"),
        `${surface.name} credits Yahoo for a league imported from Sleeper`,
      ).toHaveCount(0)
      await expect(page.getByText(/Fantasy data provided by Yahoo/)).toHaveCount(0)

      expectNoPageErrors(errors)
    })
  })
}

test.describe("the import screen credits Yahoo before a league is even previewed", () => {
  test("⭐ the LEAGUE LIST is already Yahoo's data, and is credited on sight", async ({ page }) => {
    // ⚠️ THE LIST IS THE POINT. League names, team counts, season and status all come straight from
    // Yahoo's API, and Half A rendered the credit only inside the PREVIEW block — so this screen
    // showed their data uncredited for the whole time a user spends choosing which league to
    // import, which is the longest they look at it. The Cover Page says "each page where Yahoo
    // Fantasy Information is displayed", not "each page where it is displayed in detail".
    const errors = collectPageErrors(page)
    await signIn(page, { groups: [] })
    await mockApi(page, { entitlement: "free", leagues: "none", yahoo: "connected" })
    await page.goto("/fantasy/import?yahoo=connected")
    await page.getByRole("button", { name: /Yahoo/ }).first().click()
    await page.getByRole("button", { name: /Load my Yahoo leagues/ }).click()

    // Non-vacuity first: the list has to actually be on screen, or "credited" means nothing.
    await expect(page.getByTestId("import-league-option").first()).toBeVisible()
    const link = attribution(page).getByRole("link", { name: /Fantasy data provided by Yahoo/ })
    await expect(
      link,
      "the Yahoo league list is on screen with no attribution in the footer",
    ).toBeVisible()
    await expect(link).toHaveAttribute("href", /fantasysports\.yahoo\.com/)

    expectNoPageErrors(errors)
  })

  test("a visitor who has not connected Yahoo sees no credit", async ({ page }) => {
    // The control. Without it, an import page that credited Yahoo unconditionally — before the user
    // has connected anything, on a screen showing none of their data — would pass the case above.
    const errors = collectPageErrors(page)
    await signIn(page, { groups: [] })
    await mockApi(page, { entitlement: "free", leagues: "none" })
    await page.goto("/fantasy/import")

    await expect(page.getByTestId("platform-attribution")).toHaveCount(0)

    expectNoPageErrors(errors)
  })
})

test.describe("a deleted roster says it was deleted", () => {
  test("⭐ a purged league is not explained as a league that never drafted", async ({ page }) => {
    // ⚠️ THE TWO STATES ARE THE SAME PAYLOAD. A disconnected league and a league whose draft has not
    // happened both arrive as "team linked, roster empty", and until `roster_retention_purged` was
    // served, My Teams explained BOTH as "the usual reason is your league hasn't drafted yet" — a
    // confident wrong answer for something we did, telling the user to re-import to fix a
    // non-problem. NF-C6b's ambiguous-empty-state defect, on the deletion path.
    const errors = collectPageErrors(page)
    await signIn(page, { groups: ["subscriber"] })
    await mockApi(page, { entitlement: "entitled", leagues: "yahooPurged" })
    await page.goto("/fantasy/my-teams")
    await expect(page.getByRole("heading", { name: "My Teams" })).toBeVisible()

    const notice = page.getByTestId("roster-retention-purged")
    await expect(notice, "a purged league gave no account of where its roster went").toBeVisible()
    await expect(notice).toContainText(/deleted the roster/i)
    // The window has to be NAMED. "We deleted it at some point" is not a retention statement.
    await expect(notice).toContainText(/30-day retention window/i)
    // And the settings surviving is the half a user will not assume.
    await expect(notice).toContainText(/scoring settings are untouched/i)

    await expect(
      page.getByText(/hasn.t drafted yet/),
      "a deletion we performed is still being explained as the league not having drafted",
    ).toHaveCount(0)

    expectNoPageErrors(errors)
  })

  test("a genuinely pre-draft league still gets the pre-draft explanation", async ({ page }) => {
    // The control for the case above: the branch that was wrong for purged leagues is RIGHT here,
    // and a fix that simply deleted it would pass the previous test while making this surface
    // silent about the ordinary state most users are actually in.
    const errors = collectPageErrors(page)
    await signIn(page, { groups: ["subscriber"] })
    await mockApi(page, { entitlement: "entitled", leagues: "predraft" })
    await page.goto("/fantasy/my-teams")
    await expect(page.getByRole("heading", { name: "My Teams" })).toBeVisible()

    await expect(page.getByText(/hasn.t drafted yet/)).toBeVisible()
    await expect(page.getByTestId("roster-retention-purged")).toHaveCount(0)

    expectNoPageErrors(errors)
  })
})
