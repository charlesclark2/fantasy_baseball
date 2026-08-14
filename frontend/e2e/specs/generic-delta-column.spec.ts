import { expect, test, type Page } from "@playwright/test"
import { collectPageErrors, mockApi, type MockOptions } from "../support/api-mock"
import { signIn } from "../support/session"
import { expectNoNaN, expectNoPageErrors } from "../support/assertions"

/**
 * E9.61 — the "vs our generic board" delta ON THE BROWSE BOARDS.
 *
 * ══ WHAT ONLY A BROWSER CAN ANSWER HERE ════════════════════════════════════════════════════════
 *
 *   1. ⭐ THE GATE. Rankings is a PUBLIC route, and this column renders PERSONALIZATION. The claim
 *      that an anonymous visitor can never see it is structural (no token → no saved leagues → no
 *      `custom:` selection), but "structural" is exactly the kind of argument that stops being true
 *      when someone changes a default. Only a real anonymous page load proves it.
 *   2. THE SCALE. A position tab ranks WITHIN the position, so the move beside it must be the move
 *      within the position. Rendering the OVERALL move there is arithmetically wrong and looks
 *      completely normal — the same trap `adpPositionRanks` exists for. Two renderings of the same
 *      player, on two tabs, is the only way to tell the two implementations apart.
 *   3. THE SELECTION SURVIVING A RELOAD. Measured broken while building this story: a free account
 *      picked its league, the board and the delta rendered, and a reload silently reverted to the
 *      generic preset. Nothing errored. It is a two-request race (`useFormatSelection`'s
 *      `savedLeaguesLoading`), so it reproduces only against a real server with real timing.
 *
 * ⛔ WHAT IT DOES NOT PROVE. That the delta's NUMBERS are right in production. The two fixture
 * boards are on incompatible point scales — the generic board's `pts` are the synthetic `fpPpr`
 * field, while the league board is re-scored in the browser from independently-seeded synthetic RAW
 * STATS (measured: D/ST at 3,187 pts against a generic-board maximum of 338). Both are internally
 * consistent and neither is real, so magnitudes here are meaningless and nothing below asserts on
 * one. `free-league.spec.ts` carries the arithmetic check, anchored on values re-derived from the
 * served payloads rather than on the delta's own output.
 */

const DELTA_LABEL = "vs our generic board"
const SAVED_LEAGUE = /Sunday Money/

/** Open a browse board as a signed-in free account holding one saved league. */
async function open(page: Page, path: string, groups: string[] = [], extra: MockOptions = {}) {
  await signIn(page, { groups })
  const errors = collectPageErrors(page)
  const mock = await mockApi(page, { entitlement: "free", leagues: "one", ...extra })
  await page.goto(path)
  return { errors, mock }
}

/** Switch the format picker onto the caller's saved league. */
async function selectSavedLeague(page: Page) {
  await page.getByLabel("Scoring format").click()
  await page.getByRole("option", { name: SAVED_LEAGUE }).click()
  await expect(page.getByTestId("generic-delta-band")).toBeVisible()
}

/** The table's header cells, as text. */
const headers = (page: Page) => page.locator("table thead th")

test.describe("the delta column is gated on having a league of your own", () => {
  test("an ANONYMOUS visitor to the public Rankings gets no delta, and never asks for one", async ({
    page,
  }) => {
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, { entitlement: "free", leagues: "none" })
    await page.goto("/fantasy/rankings")
    await expect(page.locator("table tbody tr").first()).toBeVisible()

    // The two renderers, both absent.
    await expect(page.getByTestId("generic-delta-band")).toHaveCount(0)
    await expect(headers(page).filter({ hasText: DELTA_LABEL })).toHaveCount(0)

    // ⭐ AND THE COST HALF, which the render assertions above cannot see. The generic board is
    // fetched to COMPARE against; on a preset there is nothing to compare, so the request must not
    // be issued at all. Rankings is the landing surface for anonymous traffic, and a second board
    // read per view would hand back a chunk of what G100-D1 saved. `useFantasyBoard` is inert only
    // while it is passed nulls — a component that fetched unconditionally and hid the column would
    // pass every assertion above.
    const boardCalls = mock.requested.filter((r) => r.startsWith("/fantasy/nfl/board"))
    expect(boardCalls.length, "the anonymous board read is missing entirely").toBe(1)

    // The saved-league read is what a `custom:` selection would need, and an anonymous caller has
    // no token — so it must never be attempted.
    expect(
      mock.requested.filter((r) => r.startsWith("/fantasy/leagues")),
      "an anonymous visitor reached for saved leagues",
    ).toEqual([])
    expectNoPageErrors(errors)
  })

  test("a signed-in account on a PRESET gets no delta either", async ({ page }) => {
    // Not a gating case — a correctness one. On the generic preset the "generic board" IS the board
    // on screen, so the column would be a wall of zeroes dressed up as a comparison.
    const { errors } = await open(page, "/fantasy/rankings")
    await expect(page.locator("table tbody tr").first()).toBeVisible()
    await expect(page.getByTestId("generic-delta-band")).toHaveCount(0)
    await expect(headers(page).filter({ hasText: DELTA_LABEL })).toHaveCount(0)
    expectNoPageErrors(errors)
  })
})

test.describe("Rankings, with the caller's own league selected", () => {
  test("the band and the column arrive, under the label that says what they compare", async ({
    page,
  }) => {
    const { errors } = await open(page, "/fantasy/rankings")
    await expect(page.locator("table tbody tr").first()).toBeVisible()
    await selectSavedLeague(page)

    // ⭐ THE LABEL IS THE ASSERTION, not merely that a column appeared. Every other delta column in
    // this product means "versus ADP"; an unlabelled one inherits that reading, which would turn a
    // comparison between two of our own boards into an implied claim about the market.
    await expect(headers(page).filter({ hasText: DELTA_LABEL })).toHaveCount(1)

    const band = page.getByTestId("generic-delta-band")
    await expect(band).toContainText("Sunday Money")
    // The honesty sentence rides on the surface, not only in the tooltip.
    await expect(band).toContainText(/not (a view on where anyone else is drafting|from where)/)

    // The summary counts a real population rather than rendering "0 of 0".
    const [moved, compared] = (
      (await page.getByTestId("generic-delta-summary").textContent()) ?? ""
    ).match(/\d+/g)?.map(Number) ?? []
    expect(compared, "nothing was compared against the generic board").toBeGreaterThan(100)
    expect(moved).toBeLessThanOrEqual(compared)

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("the move is on the scale the RANK column is on, and changes with the tab", async ({
    page,
  }) => {
    // ⭐ THE TWO-SCALES TRAP. On a position tab the visible rank is 1..n WITHIN the position, so an
    // OVERALL move printed beside it compares two different scales — wrong, and normal-looking.
    //
    // The assertion is a COMPARISON OF TWO RENDERINGS of the same player rather than a value read
    // back from the component: an implementation that used the overall move on every tab would
    // print the SAME cell on both, so the inequality is what a single-scale bug cannot satisfy.
    const { errors } = await open(page, "/fantasy/rankings")
    await expect(page.locator("table tbody tr").first()).toBeVisible()
    await selectSavedLeague(page)

    // ⚠️ THE COLUMN IS FOUND BY ITS HEADER, NEVER BY POSITION — and this is not tidiness, it is the
    // bug the red proof caught. The first cut read `td.last()`, which is the delta on a POSITION tab
    // but is "Pos rank" on the Overall tab (that column only renders there, and it renders AFTER the
    // delta). So the test compared a delta against a rank, found them different, and passed —
    // including with the scale deliberately broken. It asserted nothing.
    const deltaColumn = async () => {
      const labels = await headers(page).allInnerTexts()
      const idx = labels.findIndex((h) => h.includes(DELTA_LABEL))
      expect(idx, "the delta column is not on this tab — the anchor is missing").toBeGreaterThan(-1)
      return idx
    }
    const deltaCellFor = async (name: string) => {
      const idx = await deltaColumn()
      const row = page.locator("table tbody tr", { hasText: name }).first()
      await expect(row).toBeVisible()
      return (await row.locator("td").nth(idx).innerText()).trim()
    }

    await page.getByRole("button", { name: "TE", exact: true }).click()
    await expect(headers(page).filter({ hasText: DELTA_LABEL })).toHaveCount(1)
    const firstTe = await page
      .locator("table tbody tr")
      .first()
      .locator("td")
      .nth(2)
      .innerText()
    const onPositionTab = await deltaCellFor(firstTe)

    await page.getByRole("button", { name: "Overall", exact: true }).click()
    const onOverallTab = await deltaCellFor(firstTe)

    expect(
      onPositionTab,
      `${firstTe} shows the same move on the TE tab (${onPositionTab}) as on Overall ` +
        `(${onOverallTab}) — the column is not following the rank scale it sits beside`,
    ).not.toBe(onOverallTab)
    expectNoPageErrors(errors)
  })

  test("the selection — and the delta — survive a reload", async ({ page }) => {
    // ⭐ MEASURED BROKEN, and silently: `useFormatSelection` committed its choice on the first
    // manifest and locked itself out, so a `custom:` value restored from storage lost the race
    // against the saved-league request and the caller was put back on the generic preset. The
    // column this whole story adds simply vanished on the second visit.
    //
    // ⭐ E9.64 — THE SAVED-LEAGUE READ IS HELD BACK ON PURPOSE, and without it this test could not
    // be trusted in either direction. Against a local server the manifest and the saved-league read
    // land within a few milliseconds of each other, so a build with the deferral REMOVED lost the
    // race only sometimes: the red proof for this case returned RED on one run and MISMATCH on the
    // next, from identical code. A falsifiability harness that answers differently run to run is
    // worse than one that fails, because a single green reads as proof.
    //
    // The delay makes the manifest win every time, which is precisely the ordering the deferral
    // exists to survive. It cannot mask a regression: the guard's whole job is to WAIT for this
    // read, so a correct build passes at any delay and a broken one now fails at every one.
    const { errors } = await open(page, "/fantasy/rankings", [], {
      delay: { paths: ["/fantasy/leagues"], ms: 400 },
    })
    await expect(page.locator("table tbody tr").first()).toBeVisible()
    await selectSavedLeague(page)

    await page.reload()
    await expect(page.locator("table tbody tr").first()).toBeVisible()
    await expect(
      page.getByTestId("generic-delta-band"),
      "the personalized board did not survive a reload",
    ).toBeVisible()
    await expect(page.getByLabel("Scoring format")).toContainText("Sunday Money")
    expectNoPageErrors(errors)
  })
})

test.describe("the League Board carries the same column", () => {
  test("a member on their own league sees the band and the labelled column", async ({ page }) => {
    // `subscriber`, because `/fantasy/league-board` is `FantasyGuard`-gated. The picker renders off
    // the manifest, so the saved league is selectable even though the harness refuses the paid
    // preset this surface defaults to.
    const { errors } = await open(page, "/fantasy/league-board", ["subscriber"])
    await expect(page.getByLabel("Scoring format")).toBeVisible()
    await selectSavedLeague(page)

    await expect(headers(page).filter({ hasText: DELTA_LABEL })).toHaveCount(1)
    await expect(page.getByTestId("generic-delta-band")).toContainText("Sunday Money")
    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })
})
