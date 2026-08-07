import { expect, test, type Page } from "@playwright/test"
import { collectPageErrors, mockApi } from "../support/api-mock"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"

/**
 * THE EXPECTED-POINTS LABEL, at the render level.
 *
 * THE DEFECT THIS PAGE HAD. Our published point total is an EXPECTED season total — the chance a
 * player misses games is multiplied through it — so it sits structurally below both an "if he
 * plays every week" projection and a healthy player's finished season. On the public track record
 * that put an unlabelled 236 next to a real 371 in the same row, and the only available reading
 * was "the model is broken". It is not; the number was shipped with nothing beside it saying so.
 *
 * ⭐ WHY THIS NEEDS A BROWSER AT ALL. `betting_ml/tests/test_expected_points_label_copy.py` proves
 * the COPY is honest and that every surface's source binds the canonical constant. Neither is the
 * property that matters to a reader, and both are satisfiable by a page that never renders:
 *
 *   1. THE DEFINITION MUST OPEN ON TAP. `InfoTip` is built on Radix Popover precisely because
 *      Tooltip closes on pointerdown and can therefore never be opened by a touch. A source scan
 *      sees `<InfoTip>` either way; only a real tap distinguishes them, and a phone reader who
 *      cannot open the definition is the exact reader this story exists for.
 *   2. THE GAMES VALUE MUST REACH THE ROW. `projGames` is a new key on a payload the frontend
 *      ships ahead of (the artifact grows it at the operator's post-merge `--publish`), and the
 *      most likely failure is a rendered em-dash column — which looks deliberate and proves
 *      nothing. So the assertion is on a real NUMBER in a named player's row.
 */

async function renderedText(page: Page): Promise<string> {
  return (await page.locator("body").innerText()).replace(/\s+/g, " ")
}

/**
 * ⚠️ WAIT FOR THE FETCHED CONTENT BEFORE READING THE PAGE — the CI-only flake NF-TR1 shipped and
 * had to fix. A whole-page text snapshot taken straight after `goto` can capture the LOADING
 * state, in which the label and the table are legitimately absent, and the test then reports a
 * product defect for its own race. It weakens nothing: a page that never renders the table still
 * fails here, on the wait, with a clearer message.
 */
async function gotoTrackRecord(page: Page) {
  await page.goto("/fantasy/track-record")
  await expect(page.locator("table tbody tr").first()).toBeVisible()
}

/** The season table (not the position-split or context-benchmark tables above it). */
function seasonTable(page: Page) {
  return page.locator("table").filter({ hasText: "Actual pts" })
}

test.describe("public Track Record — the points column is labelled as EXPECTED", () => {
  test("the projected-points column is headed as expected points, not as a bare projection", async ({
    page,
  }) => {
    const errors = collectPageErrors(page)
    const mock = await mockApi(page)
    await gotoTrackRecord(page)

    const header = seasonTable(page).locator("thead")
    await expect(header).toContainText("Expected pts")
    // ⛔ …and the retired wording is genuinely GONE, not merely joined by a better one. A header
    // carrying both would leave the original misread intact for anyone reading the first label.
    await expect(header).not.toContainText("Our pts")

    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("the definition opens on TAP and explains the discount without overclaiming", async ({
    page,
  }) => {
    // ⭐ THE CLAUSE A SOURCE SCAN CANNOT MAKE — but it only makes it on the `mobile` project, and
    // that is not a nicety. On desktop Chromium `click()` dispatches `pointerenter` first, and
    // `InfoTip` opens on hover for a mouse — so the popover is already open before the click
    // lands, and a Radix TOOLTIP (which no touch can ever open) would pass this test identically.
    // On the Pixel 7 project there is no hover and `pointerType` is "touch", so the only thing
    // that can open the definition is the tap. See `playwright.config.ts`'s `testMatch`.
    const errors = collectPageErrors(page)
    const mock = await mockApi(page)
    await gotoTrackRecord(page)

    await seasonTable(page).getByRole("button", { name: /Expected pts/i }).click()

    // ⚠️ Scoped to the POPOVER, not to the text. The page's own explanatory note says something
    // very similar a few hundred pixels up, so a bare text match is satisfied whether or not the
    // tap did anything — and this test's entire subject is whether the tap did anything.
    const definition = page.getByRole("dialog")
    await expect(definition, "the expected-points definition did not open on tap").toBeVisible()

    const text = await definition.innerText()
    expect(text.toLowerCase(), "the definition does not name missed games as what is priced in")
      .toMatch(/miss(es|ed) games/)
    expect(text.toLowerCase(), "the definition does not tell the reader our number is lower")
      .toContain("lower")

    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("projected games renders as a real number beside the points, per player", async ({
    page,
  }) => {
    // ⛔ NOT "the column exists". An em-dash column renders, looks intentional, and explains
    // nothing — it is the single most likely way this ships broken, because `projGames` is a new
    // key the frontend deploys ahead of. So: a NAMED player, and his actual value.
    //
    // ⭐ Bijan Robinson is the row the story was reported on — 236.2 expected against a 370.8
    // finish. His 15.0 projected games is also the honest half of the point: it does NOT close
    // that gap, which is why the page's note refuses to claim availability explains everything.
    const errors = collectPageErrors(page)
    const mock = await mockApi(page)
    await gotoTrackRecord(page)

    await page.getByRole("button", { name: /^RB$/ }).click()
    const row = seasonTable(page).locator("tbody tr", { hasText: "Bijan Robinson" })
    await expect(row).toBeVisible()

    const cells = row.locator("td")
    const points = (await cells.nth(3).innerText()).trim()
    const games = (await cells.nth(4).innerText()).trim()

    expect(points, "the expected-points cell is not the served value").toBe("236.2")
    expect(games, "projected games rendered as an em-dash — the value never reached the row")
      .toBe("15.0")

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("the page explains the discount as availability WITHOUT claiming it explains everything", async ({
    page,
  }) => {
    // ⭐⭐ THE CLAUSE THAT KEEPS THIS STORY HONEST, and the pair is deliberate: an availability
    // explanation is only publishable BECAUSE the hedge ships with it. Availability carries most
    // of the measured level shift and not all of it — a residual remains at the worst position and
    // it is a real miscalibration with its own model story. Asserting only the explanation would
    // let a later edit drop the hedge and turn an honest disclosure into a cover.
    const mock = await mockApi(page)
    await gotoTrackRecord(page)
    const text = (await renderedText(page)).toLowerCase()

    expect(text, "the page does not explain that the points column prices in missed games")
      .toContain("chance a player misses games is already priced into the number")
    expect(text, "the page dropped the hedge — it now reads as though availability accounts for " +
      "the whole difference, which it does not")
      .toContain("not the only reason a projection lands under a finished season")

    // ⛔ …and it is a DISCLOSURE, not an apology. "by design, not by accident" is the sentence
    // that makes the lower number a reason to trust us rather than something to excuse.
    expect(text, "the framing no longer states the discount is deliberate")
      .toContain("by design, not by accident")

    expectApiFullyMocked(mock)
  })

  test("the explanation arrives ABOVE the table that prompts the question", async ({ page }) => {
    // An explanation a reader meets after the row that confused them is not an explanation. This
    // is the same geometry rule NF-TR1's "calibration leads" test applies one block up.
    const mock = await mockApi(page)
    await gotoTrackRecord(page)

    const noteBox = await page.getByText("Why our points column runs below").first().boundingBox()
    const tableBox = await seasonTable(page).first().boundingBox()
    expect(noteBox, "the expected-points note is not laid out").not.toBeNull()
    expect(tableBox, "the season table is not laid out").not.toBeNull()
    expect(
      noteBox!.y,
      "the points explanation renders below the table it explains, where the reader meets the " +
        "confusing row first",
    ).toBeLessThan(tableBox!.y)

    expectApiFullyMocked(mock)
  })

  test("nothing the labelling added makes a forbidden claim", async ({ page }) => {
    // The new copy ships on the PUBLIC track record beside a claim whose own interval includes
    // zero, so it answers to the same screen as the claim — and it is static component copy, which
    // is precisely the category no export-side denylist has ever seen.
    const mock = await mockApi(page)
    await gotoTrackRecord(page)
    await seasonTable(page).getByRole("button", { name: /Expected pts/i }).click()

    const hits = forbiddenPhrasesIn(await renderedText(page))
    expect(hits, `the expected-points copy makes a forbidden claim: ${hits.join(", ")}`).toEqual([])

    expectApiFullyMocked(mock)
  })

  test("⛔ no surface cites the outcome-bucketed decile comparison", async ({ page }) => {
    // Sorting players by their REALIZED finish and comparing per-decile means produces a
    // compression pattern even for a perfectly calibrated projection — the top realized decile is
    // selected for positive noise. It cannot distinguish bias from correct shrinkage, so it is
    // evidence of nothing, and it is the most dramatic-looking table in the memo behind this work
    // — i.e. exactly what a future copy edit would reach for.
    const mock = await mockApi(page)
    await gotoTrackRecord(page)
    const text = (await renderedText(page)).toLowerCase()

    for (const phrase of ["decile", "top 10% of finishers"]) {
      expect(text, `the page cites the outcome-bucketed decile comparison (${phrase})`)
        .not.toContain(phrase)
    }

    expectApiFullyMocked(mock)
  })

  test("an artifact published before this story still renders, with no invented games figure", async ({
    page,
  }) => {
    // ⚠️ THE DEPLOY-SKEW RENDER, and it is the live state on merge day: `frontend/` deploys on
    // merge while `projGames` only lands at the operator's post-merge `--publish`. The label and
    // the explanation must still render (they are static copy and do not depend on the payload),
    // and the games column must degrade to an em-dash.
    //
    // ⛔ The failure this forbids is a FALLBACK. A `?? 17`, or anything derived from `ourPoints`,
    // would render a confident games figure on precisely the rows where we have none — making the
    // discount look accounted for when it cannot be. An em-dash is the honest render.
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, {
      transform: (pathname, body) =>
        pathname === "/fantasy/nfl/track-record/2025"
          ? (body as any[]).map(({ projGames, ...rest }) => rest)
          : body,
    })
    await gotoTrackRecord(page)

    await expect(seasonTable(page).locator("thead")).toContainText("Expected pts")
    await expect(page.getByText("Why our points column runs below")).toBeVisible()

    await page.getByRole("button", { name: /^RB$/ }).click()
    const row = seasonTable(page).locator("tbody tr", { hasText: "Bijan Robinson" })
    expect((await row.locator("td").nth(4).innerText()).trim(), "a games figure was invented for " +
      "a payload that carries none").toBe("—")

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })
})
