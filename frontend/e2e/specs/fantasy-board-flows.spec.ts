import { expect, test, type Page } from "@playwright/test"
import { FIXTURES, collectPageErrors, mockApi } from "../support/api-mock"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"

/**
 * E9.64 — THE FREE BOARD, ACTUALLY USED.
 *
 * ══ THE GAP THIS CLOSES ═══════════════════════════════════════════════════════════════════════
 *
 * `freemium-board.spec.ts` proves the board RENDERS for a stranger and that the format controls are
 * locked correctly. Every one of its assertions is about the board's opening state. But a visitor
 * who came for a ranking does not read 858 rows in served order — they filter to a position, they
 * search a name, they page, and they click through to a player. None of that was driven anywhere,
 * and it is where the failures live:
 *
 *   · a filter that narrows the ROWS but not the RANKS, so the reader gets QBs numbered 1..105 that
 *     are really overall ranks — or the reverse. Nothing type-checks this.
 *   · `NaN` — E9.56b's whole class — which appears on INTERACTION, not on first paint. The existing
 *     specs scan a board nobody has touched.
 *   · a search that matches nothing rendering an empty table rather than saying so (the same
 *     silent-empty shape the harness exists to catch).
 *   · a player cell whose link goes to a page about a DIFFERENT player, which every "the player
 *     page renders" assertion passes.
 *
 * ══ THE METHOD: ASSERT AGAINST THE SERVED PAYLOAD, NEVER AGAINST A NAME ═══════════════════════
 *
 * The board is re-published constantly, so a spec naming a player is a spec with a shelf life. Every
 * assertion below reads the fixture — the same bytes the page was served — and cross-checks the
 * RENDERED rows against it. That is also what makes the position filter assertion meaningful: the
 * question is not "did the row count change" but "is every surviving row genuinely a QB according
 * to the payload", which a filter applied to the wrong field would fail.
 *
 * ⚠️ ANONYMOUS THROUGHOUT. No session is seeded: this is the acquisition surface, and the visitor it
 * describes has never signed in.
 */

/** `id → pos`, straight out of the board the page was served. */
function boardPositions(): Map<string, string> {
  return new Map((FIXTURES.boardFree() as any[]).map((p) => [p.id, p.pos]))
}

/** `id → pos` for the projections payload, which Projections and Player Search read instead. */
function projectionPositions(): Map<string, string> {
  return new Map((FIXTURES.projectionsEntitled().players as any[]).map((p) => [p.id, p.pos]))
}

/** The player ids the page is CURRENTLY showing, read off the row links rather than the text.
 *
 *  ⭐ IDS, NOT NAMES. Two players can share a name and a name can be re-rendered (E9.61 found two
 *  independent name-casing passes in this codebase); the id in the href is what the row actually
 *  resolves to, and it is also what the click-through has to match. */
async function visiblePlayerIds(page: Page, scope = "table tbody"): Promise<string[]> {
  return page
    .locator(`${scope} a[href^="/fantasy/player/"]`)
    .evaluateAll((els) =>
      els.map((e) => ((e as HTMLAnchorElement).getAttribute("href") ?? "").split("/").pop() ?? ""),
    )
}

/**
 * How many rows the board says it holds, read off the pagination range (`1–50 of 858`).
 *
 * ⚠️ THIS, NOT THE VISIBLE ROW COUNT, IS WHAT A FILTER MOVES — and getting that wrong is a false
 * GREEN waiting to happen. The board pages at 50, so filtering 858 players down to 105 quarterbacks
 * leaves the number of RENDERED rows at exactly 50 either way: an assertion that the visible count
 * shrank passes only by accident on a position with fewer than 50 players, and silently proves
 * nothing on QB, RB, WR or TE.
 */
async function boardTotal(page: Page): Promise<number> {
  const text = await page.getByText(/\d+–\d+ of [\d,]+/).first().innerText()
  const m = text.match(/of ([\d,]+)/)
  if (!m) throw new Error(`e2e: no pagination total in "${text}"`)
  return Number(m[1].replace(/,/g, ""))
}

/** Wait for the board to have rows, so nothing below reads a loading state. */
async function openBoard(page: Page, path: string) {
  const errors = collectPageErrors(page)
  const mock = await mockApi(page, { entitlement: "free" })
  await page.goto(path)
  await expect(page.locator("table tbody tr").first()).toBeVisible()
  return { errors, mock }
}

test.describe("Rankings — filtering, searching and paging the free board", () => {
  test("the position filter leaves only that position, and nothing else on the page breaks", async ({
    page,
  }) => {
    const { errors, mock } = await openBoard(page, "/fantasy/rankings")
    const positions = boardPositions()

    const before = await visiblePlayerIds(page)
    expect(before.length, "the board rendered no player links at all").toBeGreaterThan(0)
    const totalBefore = await boardTotal(page)

    // `allLabel="Overall"` on this surface, so the tabs read Overall / QB / RB / …
    await page.getByRole("button", { name: "QB", exact: true }).click()

    // ⏳ Auto-retrying: the filter is React state, so the rows repaint after the click resolves.
    // A single-shot read here is the `locator.count()` race G100-D0-R1 was bitten by.
    await expect
      .poll(async () => (await visiblePlayerIds(page)).length, {
        message: "the QB filter left no rows — it matched nothing, or the board was emptied",
      })
      .toBeGreaterThan(0)

    const after = await visiblePlayerIds(page)
    // ⭐ THE ASSERTION THAT MATTERS. "Fewer rows" is satisfied by a filter keyed on the wrong field,
    // by an off-by-one slice, and by a search box that happened to be dirty. "Every remaining row
    // is a QB in the payload we were served" is satisfied by exactly one thing.
    const wrong = after.filter((id) => positions.get(id) !== "QB")
    expect(
      wrong.slice(0, 5),
      `the QB filter kept ${wrong.length} rows that are not quarterbacks in the served board`,
    ).toEqual([])
    // The board's own count of what it now holds — see `boardTotal` for why the visible row count
    // is the wrong instrument here.
    const totalAfter = await boardTotal(page)
    expect(totalAfter, "filtering to one position did not narrow the board").toBeLessThan(
      totalBefore,
    )
    expect(totalAfter, "the QB filter emptied the board").toBeGreaterThan(0)

    // Interaction is exactly when the E9.56b arithmetic class shows up — the untouched board these
    // other specs scan is the state in which it is least likely to appear.
    await expectNoNaN(page)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("searching a name narrows the board to that player, and clearing it restores the board", async ({
    page,
  }) => {
    const { errors } = await openBoard(page, "/fantasy/rankings")
    const board = FIXTURES.boardFree() as any[]
    // Read the subject out of the payload; a hardcoded name goes stale on the next publish.
    const target = board[0]

    const search = page.getByPlaceholder("Search player")
    await search.fill(target.name)
    await expect
      .poll(async () => await visiblePlayerIds(page), {
        message: `searching "${target.name}" never surfaced that player's own row`,
      })
      .toContain(target.id)

    const matched = await visiblePlayerIds(page)
    // Every surviving row genuinely contains the needle — a search that widened, or that ignored
    // the box entirely, fails here rather than passing on "the player is somewhere on the page".
    const byId = new Map(board.map((p) => [p.id, p.name]))
    const spurious = matched.filter(
      (id) => !(byId.get(id) ?? "").toLowerCase().includes(target.name.toLowerCase()),
    )
    expect(spurious.slice(0, 5), "the search returned rows that do not match the query").toEqual([])

    // ⭐ THE OTHER HALF, and it is the one that actually strands a reader: a search box that cannot
    // be un-typed leaves them on a one-row board with no way back to what they came for.
    await search.fill("")
    await expect
      .poll(async () => (await visiblePlayerIds(page)).length, {
        message: "clearing the search box did not bring the board back",
      })
      .toBeGreaterThan(matched.length)

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("a search that matches nothing says so, rather than rendering an empty table", async ({
    page,
  }) => {
    // The silent-empty class. ⚠️ And it must say the SEARCH found nothing — `freemium-board.spec.ts`
    // holds the mirror case, where a refused PAID board must NOT fall through to this message. The
    // two states share a zero-row table and are completely different facts, so both need pinning or
    // one can be "fixed" into the other.
    const { errors } = await openBoard(page, "/fantasy/rankings")

    await page.getByPlaceholder("Search player").fill("zzzznotaplayerzzzz")

    await expect(
      page.getByText("No players match"),
      "a search with no results rendered nothing at all — indistinguishable from a broken board",
    ).toBeVisible()
    await expect(page.locator("table tbody tr")).toHaveCount(0)
    expectNoPageErrors(errors)
  })

  test("paging advances through the board and keeps counting from where it left off", async ({
    page,
  }) => {
    const { errors } = await openBoard(page, "/fantasy/rankings")

    const firstPage = await visiblePlayerIds(page)
    expect(firstPage.length, "the first page rendered no rows").toBeGreaterThan(0)

    // The range indicator is the reader's only statement of WHERE they are in 858 rows, so it is
    // what the assertion is anchored on. `1–50 of 858` → `51–100 of 858`.
    const total = firstPage.length
    await expect(page.getByText(new RegExp(`^1–${total} of `)).first()).toBeVisible()

    await page.getByRole("button", { name: "Next", exact: true }).first().click()

    await expect
      .poll(async () => (await visiblePlayerIds(page))[0], {
        message: "Next did not advance the board — the same row is still at the top",
      })
      .not.toBe(firstPage[0])

    const secondPage = await visiblePlayerIds(page)
    // No overlap: a slice that forgot to offset, or that re-sorted, shows some of page one again.
    const repeated = secondPage.filter((id) => firstPage.includes(id))
    expect(repeated.slice(0, 5), "page two repeated rows from page one").toEqual([])
    await expect(
      page.getByText(new RegExp(`^${total + 1}–`)).first(),
      "the range indicator restarted instead of continuing — the reader cannot tell where they are",
    ).toBeVisible()

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })
})

test.describe("Projections — the same controls on the other public board", () => {
  // Not redundant with the block above: these are DIFFERENT components reading a DIFFERENT endpoint
  // (`/fantasy/nfl/projections` rather than `/fantasy/nfl/board`), with their own filter state and
  // their own default position label. The E9.56b/E9.56c pattern in this repo is a fix landing on
  // one of the two surfaces and not the other — #681 locked the board's format picker and left the
  // projections one open for the whole of that PR's life.
  test("the position filter leaves only that position", async ({ page }) => {
    const { errors, mock } = await openBoard(page, "/fantasy/projections")
    const positions = projectionPositions()

    const before = await visiblePlayerIds(page)
    expect(before.length).toBeGreaterThan(0)
    const totalBefore = await boardTotal(page)

    await page.getByRole("button", { name: "TE", exact: true }).click()
    await expect
      .poll(async () => (await visiblePlayerIds(page)).length)
      .toBeGreaterThan(0)

    const after = await visiblePlayerIds(page)
    const wrong = after.filter((id) => positions.get(id) !== "TE")
    expect(
      wrong.slice(0, 5),
      `the TE filter kept ${wrong.length} rows that are not tight ends in the served payload`,
    ).toEqual([])
    const totalAfter = await boardTotal(page)
    expect(totalAfter, "filtering to one position did not narrow the board").toBeLessThan(
      totalBefore,
    )
    expect(totalAfter, "the TE filter emptied the board").toBeGreaterThan(0)

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })
})

test.describe("the discovery flow — a name in, the right player page out", () => {
  test("a board row links to the page for THAT player", async ({ page }) => {
    // ⭐ THE DEFECT EVERY "THE PLAYER PAGE RENDERS" ASSERTION PASSES. If the cell binds the wrong
    // row's id — an index reused after a sort, a stale closure — the click still lands on a real,
    // perfectly-rendering player page. It is simply about somebody else, and only following the
    // link and comparing the destination against the row you clicked can see it.
    const { errors } = await openBoard(page, "/fantasy/rankings")

    // ⚠️ NOT THE FIRST ROW, and the reason is red-provability. The natural bug here is every cell
    // binding ONE row's id (a shared closure, an index reused after a sort) — and if that id is the
    // first row's, clicking the first row still lands correctly and the test passes on a broken
    // board. A row further down can only be right if the binding is per-row.
    const link = page.locator('table tbody a[href^="/fantasy/player/"]').nth(2)
    const name = (await link.innerText()).trim()
    const href = await link.getAttribute("href")
    expect(href, "the board row has no player link").toBeTruthy()

    await link.click()
    await page.waitForURL(`**${href}`)

    await expect(
      page.getByRole("heading", { name, exact: false }).first(),
      `the row for ${name} opened a page that is not about him`,
    ).toBeVisible()
    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("Player Search takes a name and opens that player's page", async ({ page }) => {
    // The only route to a player page that does not begin on a board, and the one an indexed search
    // result competes with. `freemium-board.spec.ts` proves the ROUTE is reachable logged out; it
    // never types anything into it, so the search itself — the entire reason the surface exists —
    // was undriven.
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, { entitlement: "free" })
    await page.goto("/fantasy/players")

    const target = FIXTURES.projectionsEntitled().players[0] as any
    const search = page.getByPlaceholder("Search players…")
    await expect(search).toBeVisible()
    await search.fill(target.name)

    // Results are link cards, not table rows, so the scope is the results list.
    const result = page.locator(`a[href="/fantasy/player/${target.id}"]`).first()
    await expect(result, `searching "${target.name}" produced no result for him`).toBeVisible()

    await result.click()
    await page.waitForURL(`**/fantasy/player/${target.id}`)
    await expect(
      page.getByRole("heading", { name: target.name, exact: false }).first(),
      "the search result opened a page about a different player",
    ).toBeVisible()

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("a Player Search that matches nothing says so", async ({ page }) => {
    await mockApi(page, { entitlement: "free" })
    await page.goto("/fantasy/players")
    const search = page.getByPlaceholder("Search players…")
    await expect(search).toBeVisible()
    await search.fill("zzzznotaplayerzzzz")

    await expect(
      page.getByText("No players match"),
      "an empty search rendered a blank surface instead of saying nothing matched",
    ).toBeVisible()
  })
})
