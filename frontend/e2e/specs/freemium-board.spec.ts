import { expect, test, type Page } from "@playwright/test"
import { FIXTURES, collectPageErrors, mockApi } from "../support/api-mock"
import { forbiddenPhrasesIn } from "../support/claim-denylist"
import {
  LOCK_CHIP,
  expectApiFullyMocked,
  expectNoNaN,
  expectNoPageErrors,
} from "../support/assertions"

/**
 * THE FREEMIUM BUILD — a logged-out visitor gets the WHOLE generic board, and is told plainly what
 * a membership adds.
 *
 * ══ WHY THIS SPEC EXISTS SEPARATELY FROM `locked-surfaces.spec.ts` ═══════════════════════════
 *
 * That file asserts the E9.56 render contract: given a LOCKED payload, show chips and a CTA. It is
 * still correct and still runs — the components keep their `locked` branches so withdrawing the
 * open board stays a config decision rather than a rebuild — but ⛔ it no longer describes what any
 * user receives. This file does.
 *
 * ══ WHAT ONLY A BROWSER CAN SEE HERE ════════════════════════════════════════════════════════
 *
 * `test_freemium_tier.py` proves the SERVER sends the full payload to everyone, and that the
 * components reference the right things. Neither can see:
 *
 *   · a free visitor REDIRECTED before the board renders (the guard is client-side; the API is
 *     perfectly happy). This is the funnel-killing failure and it is invisible to every Python
 *     assertion in the repo.
 *   · a padlock rendered over a value the payload CONTAINS — a paywall on free content, which
 *     converts nobody and reads as broken.
 *   · `Infinity` / `NaN` in the full-season-rate column. TypeScript cannot see either: a missing
 *     field type-checks as its declared type at runtime, and `Infinity` IS a `number`.
 *   · a denied claim reaching the rendered DOM from a component string no export-side denylist has
 *     ever looked at.
 *
 * ⚠️ ANONYMOUS MEANS ANONYMOUS. No `page.addInitScript` seeding a token anywhere in this file —
 * the visitor these specs describe has never signed in, and seeding auth would quietly turn every
 * assertion below into a statement about a logged-in free user instead.
 */

/** Table cells holding a plain number — what "the real board rendered" actually looks like. */
async function numericCellCount(page: Page): Promise<number> {
  return page
    .locator("table tbody td")
    .evaluateAll(
      (els) => els.filter((e) => /^-?\d[\d,]*(\.\d+)?$/.test((e.textContent ?? "").trim())).length,
    )
}

/** The row for one player, found through the surface's own search box rather than by index.
 *
 *  ⚠️ INDEXING WOULD BE WRONG AND WOULD LOOK RIGHT. The degenerate expected-games rows the fixture
 *  builder plants sort deep into the board once ranks follow the generated points (measured: ranks
 *  ~587–852 of 858), so they are not on page one and a positional locator would silently assert
 *  against a different, healthy player. */
async function rowFor(page: Page, playerName: string) {
  const search = page.getByPlaceholder("Search player")
  await search.fill(playerName)
  const row = page.locator("table tbody tr", { hasText: playerName }).first()
  await expect(row).toBeVisible()
  return row
}

test.describe("the free generic board", () => {
  for (const [surface, path] of [
    ["Rankings", "/fantasy/rankings"],
    ["Projections", "/fantasy/projections"],
  ] as const) {
    test(`${surface} renders the full board for a logged-out visitor`, async ({ page }) => {
      const errors = collectPageErrors(page)
      const mock = await mockApi(page)

      await page.goto(path)
      await expect(page.locator("table tbody tr").first()).toBeVisible()

      // ⭐ THE UN-GATE ITSELF. Pre-freemium this same navigation produced a board of padlocks.
      expect(
        await page.locator(LOCK_CHIP).count(),
        "a padlock rendered over a value the free payload contains",
      ).toBe(0)
      expect(
        await numericCellCount(page),
        "the free board rendered no numeric cells — it is empty or still redacted",
      ).toBeGreaterThan(100)

      // The un-gate's other failure mode: not a lock, but a bounce. A redirect leaves no error.
      expect(page.url(), "a logged-out visitor was redirected off the free board").toContain(path)

      await expectNoNaN(page)
      expectApiFullyMocked(mock)
      expectNoPageErrors(errors)
    })
  }

  test("a player page renders the real projection for a logged-out visitor", async ({ page }) => {
    // ⭐ THE SURFACE WITH THE LARGEST BEHAVIOUR CHANGE IN THIS STORY, and the one a source guard
    // can say least about. NF3.2 made the ROUTE public but split the CONTENT by entitlement: a
    // non-entitled visitor got identity + past seasons only. That dispatch is gone — everyone now
    // gets the full page — and "everyone gets the full page" is a claim only a render can settle.
    //
    // It also exercises the new fall-through: the branch key changed from WHO IS ASKING to WHAT WE
    // HAVE, so a hooks-order mistake in the rewrite would surface here as a React error rather
    // than as a type error.
    const errors = collectPageErrors(page)
    const mock = await mockApi(page)

    // The first row of the served board — read from the fixture rather than hardcoded, so a
    // re-publish cannot silently point this at a player who is no longer in the export.
    const { id, name } = FIXTURES.projectionsEntitled().players[0]
    await page.goto(`/fantasy/player/${id}`)

    await expect(page.getByRole("heading", { name, level: 1 })).toBeVisible()
    expect(page.url(), "a logged-out visitor was redirected off a player page").toContain(id)
    expect(
      await page.locator(LOCK_CHIP).count(),
      "a padlock rendered on a free player page",
    ).toBe(0)

    // The projection itself, not merely the identity header — identity alone is exactly what the
    // retired public view showed, so a page rendering only that would look right and be the bug.
    //
    // ⚠️ CASE-INSENSITIVE, deliberately: this page styles the section heading with `uppercase`, so
    // `innerText` returns "FANTASY POINTS · EXPECTED PTS" and an exact-case match fails on a page
    // that is working. A first cut asserted the literal and reported a defect that did not exist.
    const text = await page.locator("body").innerText()
    expect(text.toLowerCase(), "the player page shows no expected-points figure")
      .toContain("expected pts")

    // The rate WITH ITS VALUE, not just its label — a label over a missing number is the shape a
    // wiring bug takes here (the tile's `sub` line is dropped entirely when the value is null), and
    // it would leave the page looking finished.
    expect(text, "the full-season rate is missing from the player page")
      .toMatch(/Full-season rate: \d[\d,]*(\.\d+)?/)

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("Player Search is reachable logged out, so a player page has a door", async ({ page }) => {
    // It is the only route to a player page that does not start on a board. Gating it while the
    // player pages themselves are free leaves the free tier with a door and no handle.
    const mock = await mockApi(page)
    await page.goto("/fantasy/players")
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
    expect(page.url()).toContain("/fantasy/players")
    expectApiFullyMocked(mock)
  })
})

test.describe("the paywall boundary is explicit", () => {
  test("the free board states what a membership adds", async ({ page }) => {
    await mockApi(page)
    await page.goto("/fantasy/rankings")
    await expect(page.locator("table tbody tr").first()).toBeVisible()

    const boundary = page.getByTestId("freemium-boundary")
    await expect(boundary, "the free board states no free/paid boundary").toBeVisible()

    // ⭐ BOTH HALVES, asserted separately. The entitlement splits on two capabilities, and a block
    // naming only personalization (the easy one to write) would leave the decision-support half
    // unsold — pinned the same way in `test_freemium_tier.py`, from the copy side.
    const text = (await boundary.innerText()).toLowerCase()
    expect(text, "the personalization half is not described").toContain("scoring")
    expect(text, "the decision-support half is not described").toContain("draft")

    // It is a boundary, not a lock: the board above it is complete, so it must not claim otherwise.
    await expect(boundary.getByRole("link", { name: /membership/i })).toBeVisible()
  })

  test("the boundary LINKS to the track record and does not quote its number", async ({ page }) => {
    // ⭐ THE NF-TR1 CONTRACT, ON THE SURFACE A VISITOR NOW ACTUALLY MEETS. `UpgradeBanner` used to
    // be the conversion surface and `track-record-claim.spec.ts` holds this rule against it — but
    // that banner only renders on a LOCKED payload, which no live caller receives any more. Left
    // there alone, the rule would keep passing on a retired component while the live one quietly
    // grew a quotation of the statistic.
    //
    // The measurement is a +0.022 gap whose own 90% interval includes zero (NF-D17). Stated
    // truthfully it needs four hedges and has to close on "it could just be luck" — which persuades
    // nobody on a conversion surface and informs nobody without the table beside it. So: a LINK,
    // never a quotation.
    await mockApi(page)
    await page.goto("/fantasy/rankings")
    await expect(page.locator("table tbody tr").first()).toBeVisible()

    const boundary = page.getByTestId("freemium-boundary")
    await expect(
      boundary.getByRole("link", { name: /track record/i }),
      "the boundary offers no route to the evidence",
    ).toBeVisible()

    const text = await boundary.innerText()
    for (const fragment of [
      "modestly outperformed",
      "could just be luck",
      "rank correlation",
      "0.517",
      "0.494",
      "+0.022",
    ]) {
      expect(
        text,
        `the boundary recites the track-record measurement (${fragment}) — that belongs on the ` +
          "page that can show its working",
      ).not.toContain(fragment)
    }
  })

  test("the boundary sits BELOW the board, not above it", async ({ page }) => {
    // Position is the argument. A visitor has to see that nothing is withheld before "this is the
    // generic one" means anything; at the top it reads as a paywall on a page that has none.
    await mockApi(page)
    await page.goto("/fantasy/rankings")
    const table = page.locator("table").first()
    await expect(table).toBeVisible()

    const tableY = (await table.boundingBox())!.y
    const boundaryY = (await page.getByTestId("freemium-boundary").boundingBox())!.y
    expect(boundaryY, "the boundary renders above the board it is meant to contextualise")
      .toBeGreaterThan(tableY)
  })

  // ⚠️ "A SUBSCRIBER IS NOT ASKED TO SUBSCRIBE" IS DELIBERATELY *NOT* TESTED HERE, and the reason
  // is worth stating rather than leaving as an omission. `FreemiumBoundary` keys on the CLIENT's
  // Cognito group list, not on the payload — so an e2e assertion would need a real signed-in
  // session, and the shortcut (seeding a localStorage key and hoping the app reads it as its auth
  // source) produces a test that passes whether or not the component works: with no groups seeded
  // successfully the visitor is anonymous, the boundary renders, and a `count === 0` assertion
  // would be measuring the seed rather than the component. A test that can pass for the wrong
  // reason is worse than a documented gap.
  //
  // ⇒ that clause is carried in Python instead, where the predicate is directly readable:
  // `test_freemium_tier.py::test_the_boundary_is_not_shown_to_someone_who_already_pays`,
  // RED-proven by deleting the early return.
})

test.describe("the full-season rate", () => {
  test("renders beside the expected total", async ({ page }) => {
    await mockApi(page)
    await page.goto("/fantasy/rankings")
    await expect(page.locator("table tbody tr").first()).toBeVisible()

    const headers = await page.locator("table thead th").allInnerTexts()
    const expected = headers.findIndex((h) => h.includes("Expected pts"))
    const rate = headers.findIndex((h) => h.includes("Full-season rate"))
    expect(expected, "the expected-points column is gone").toBeGreaterThanOrEqual(0)
    expect(rate, "the full-season-rate column never rendered").toBeGreaterThanOrEqual(0)
    expect(rate, "the two readings of the same number are not adjacent").toBe(expected + 1)

    // A populated column, not merely a header — a header over an empty column is the shape a
    // wiring bug takes, and it looks like a feature that shipped.
    const firstRow = page.locator("table tbody tr").first()
    const value = (await firstRow.locator("td").nth(rate).innerText()).trim()
    expect(value, `full-season rate cell rendered "${value}"`).toMatch(/^\d[\d,]*(\.\d+)?$/)
  })

  test("a zero, null or absent expected-games figure renders an em-dash", async ({ page }) => {
    // ⭐ THE GUARD THIS FEATURE LIVES OR DIES ON, and the reason the fixture plants three
    // degenerate rows. `pts * 17 / 0` is `Infinity` — a `number`, so it survives every `!= null`
    // check a caller might write and prints "∞" beside a points column. `undefined * 17` is `NaN`.
    // Neither is visible to `tsc`; both are visible here.
    const errors = collectPageErrors(page)
    await mockApi(page)
    await page.goto("/fantasy/rankings")
    await expect(page.locator("table tbody tr").first()).toBeVisible()

    const headers = await page.locator("table thead th").allInnerTexts()
    const rate = headers.findIndex((h) => h.includes("Full-season rate"))

    // The three players the fixture builder plants at board indices 3, 4 and 5 — g of 0, null and
    // absent respectively. Looked up by NAME through the search box: they sort deep into the board.
    for (const name of ["Ja'Marr Chase", "Christian McCaffrey", "Jaxon Smith-Njigba"]) {
      const row = await rowFor(page, name)
      const cell = (await row.locator("td").nth(rate).innerText()).trim()
      expect(cell, `${name} rendered "${cell}" rather than an em-dash`).toBe("—")
    }

    await expectNoNaN(page)
    expect(
      (await page.locator("body").innerText()).includes("Infinity"),
      "a divide-by-zero reached the rendered page",
    ).toBe(false)
    expectNoPageErrors(errors)
  })
})

test.describe("the claims on the free board", () => {
  for (const path of ["/fantasy/rankings", "/fantasy/projections"]) {
    test(`${path} carries no forbidden claim`, async ({ page }) => {
      // The Python screening runs over the COPY MODULE. This runs over what the browser actually
      // renders, which also includes every static component string — headings, table labels, empty
      // states — that no export-side denylist has ever looked at.
      await mockApi(page)
      await page.goto(path)
      await expect(page.locator("table tbody tr").first()).toBeVisible()

      const text = await page.locator("body").innerText()
      expect(forbiddenPhrasesIn(text), `denied claim language on ${path}`).toEqual([])
    })
  }
})

test.describe("the paid half is still gated", () => {
  // ⭐ WITHOUT THIS BLOCK THE FILE IS SATISFIED BY MAKING EVERYTHING FREE. Every assertion above is
  // "the free thing is visible"; a change that un-gated the whole product would pass all of them.
  for (const [surface, path] of [
    ["League Board", "/fantasy/league-board"],
    ["Draft Optimizer", "/fantasy/draft"],
    ["My Teams", "/fantasy/my-teams"],
  ] as const) {
    test(`${surface} still bounces a logged-out visitor`, async ({ page }) => {
      await mockApi(page)
      await page.goto(path)
      // The guard redirects rather than rendering. Either destination is correct — /login for a
      // stranger, /subscribe for a signed-in non-subscriber — so the assertion is that we did NOT
      // stay, rather than where we went, which would over-specify a product decision.
      await page.waitForURL((url) => !url.pathname.startsWith(path), { timeout: 10_000 })
      expect(page.url(), `${surface} rendered for a logged-out visitor`).not.toContain(path)
    })
  }
})
