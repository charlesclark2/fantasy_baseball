import { expect, test, type Page } from "@playwright/test"
import { FIXTURES, collectPageErrors, mockApi } from "../support/api-mock"
import { signIn } from "../support/session"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"

/**
 * E9.64 — THE DRAFT OPTIMIZER, DRIVEN.
 *
 * ══ WHY THIS IS THE BIGGEST GAP IN THE SUITE ══════════════════════════════════════════════════
 *
 * It is the paid product's decision-support half — the thing a membership is actually bought for —
 * it is the largest component in the app, and before this file NOTHING anywhere opened it. Every
 * other fantasy surface is a rendered read; this one is a STATE MACHINE the user drives for two
 * hours while their draft is happening, and its failures are the kind no static gate can see:
 *
 *   · a drafted player who stays on the board, so he can be taken twice
 *   · a clock that does not advance, or advances to the wrong team (snake order is arithmetic)
 *   · a sort that re-orders the rows but not the values, or that silently sorts the STRING
 *   · Undo that removes the wrong pick
 *   · a board that survives a reload but loses the picks (people reload mid-draft; the whole point
 *     of persisting to localStorage is that the tab can die at pick 40)
 *
 * ⚠️ WHO CAN OPEN IT is asserted in `fantasy-entitlement-gates.spec.ts`, not here. This file signs
 * in as a subscriber and asks only whether the tool WORKS.
 *
 * ⚠️ ASSERT AGAINST THE SERVED BOARD, never against a name — the board is republished constantly.
 */

/** The draft screen renders exactly one `<table>`: the available-players board. The roster panel and
 *  the recent-picks list are `div`s.
 *
 *  ⭐ PINNED RATHER THAN ASSUMED. If a future change adds a second table, an unqualified
 *  `page.locator("table")` would start resolving to whichever came first and every assertion below
 *  would quietly describe the wrong element. `assertOneBoard` makes that a loud failure instead. */
async function assertOneBoard(page: Page) {
  await expect(
    page.locator("table"),
    "the draft screen grew a second table — the locators in this file now need scoping",
  ).toHaveCount(1)
}

type Row = { id: string; name: string; pts: number | null; vor: number | null }

/** The available board as data: id, name and both sortable columns. */
async function availableRows(page: Page): Promise<Row[]> {
  return page.locator("table tbody tr").evaluateAll((rows) =>
    rows.map((r) => {
      const cells = Array.from(r.children) as HTMLElement[]
      const link = r.querySelector('a[href^="/fantasy/player/"]') as HTMLAnchorElement | null
      const numeric = (el: HTMLElement | undefined) => {
        const t = (el?.textContent ?? "").trim()
        return t === "" || t === "—" ? null : Number(t)
      }
      return {
        id: (link?.getAttribute("href") ?? "").split("/").pop() ?? "",
        name: (link?.textContent ?? "").trim(),
        pts: numeric(cells[2]),
        vor: numeric(cells[3]),
      }
    }),
  )
}

/** Sign in as a subscriber, open the optimizer and start a draft on the default preset. */
async function startDraft(page: Page) {
  const errors = collectPageErrors(page)
  await signIn(page, { groups: ["subscriber"] })
  const mock = await mockApi(page, { entitlement: "entitled", leagues: "none" })
  await page.goto("/fantasy/draft")

  await expect(page.getByRole("heading", { name: "Draft Optimizer" })).toBeVisible()
  await page.getByRole("button", { name: "Start draft" }).click()

  await expect(page.locator("table tbody tr").first()).toBeVisible()
  await assertOneBoard(page)
  return { errors, mock }
}

test.describe("setting up and starting a draft", () => {
  test("the board opens on the chosen league with real numbers and a clock at pick one", async ({
    page,
  }) => {
    const { errors, mock } = await startDraft(page)

    const rows = await availableRows(page)
    expect(rows.length, "the available board rendered no players").toBeGreaterThan(20)
    // ⭐ Both sortable columns carry real values. A board of names with empty Pts/VOR columns
    // renders perfectly and is useless — and `—` is what a null renders as, so it would pass any
    // "the table has rows" assertion.
    expect(
      rows.filter((r) => r.pts != null).length,
      "the Pts column is empty — the board rendered names and no projections",
    ).toBeGreaterThan(20)
    expect(
      rows.filter((r) => r.vor != null).length,
      "the VOR column is empty — the value-over-replacement the tool exists to compute is missing",
    ).toBeGreaterThan(20)

    // The clock. Slot 1 on pick 1 of a snake is the user's own turn, which is what the whole
    // recommendation panel keys on.
    await expect(page.getByText(/Round 1 · Pick 1/)).toBeVisible()
    await expect(
      page.getByText(/Your pick — choose a player below/),
      "the optimizer did not know it was the user's turn on their own first-round pick",
    ).toBeVisible()

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("the recommendations come off the board that is actually loaded", async ({ page }) => {
    // A recommendation panel populated from anywhere other than the loaded board — a stale closure,
    // a different config — renders plausibly and advises on players who are not in this draft.
    const { errors } = await startDraft(page)
    const boardIds = new Set((FIXTURES.boardFree() as any[]).map((p) => p.id))

    // ⏳ An auto-retrying assertion, never `await locator.count()`. The panel is React state settling
    // after the board query resolves, so a single-shot read races it — the G100-D0-R1 flake exactly
    // (one commit, two runs minutes apart, one red one green).
    await expect(
      page.getByRole("heading", { name: /Recommended picks/ }),
      "the recommendation panel is missing on the user's own turn",
    ).toBeVisible()

    // Every player offered on the board is a player the served payload contains.
    const rows = await availableRows(page)
    const foreign = rows.filter((r) => !boardIds.has(r.id))
    expect(
      foreign.slice(0, 5).map((r) => r.name),
      "the board is offering players that are not in the payload it was served",
    ).toEqual([])
    expectNoPageErrors(errors)
  })
})

test.describe("tracking picks", () => {
  test("drafting a player takes him off the board and moves the clock on", async ({ page }) => {
    const { errors } = await startDraft(page)

    const before = await availableRows(page)
    const target = before[0]

    // On the user's own turn the row button reads "Draft"; on someone else's it reads "→ T<n>".
    await page.locator("table tbody tr").first().getByRole("button").click()

    // ⭐ HE MUST LEAVE THE BOARD. A drafted player who stays can be taken twice, and in a live draft
    // that is discovered by the room rather than by us.
    await expect
      .poll(async () => (await availableRows(page)).map((r) => r.id), {
        message: `${target.name} was drafted and is still on the available board`,
      })
      .not.toContain(target.id)

    // …and he must land somewhere the user can see. "Recent picks" is the audit trail the whole
    // session depends on; a pick that vanishes from both lists is indistinguishable from a misclick.
    await expect(
      page.getByText("Recent picks").locator("xpath=..").getByText(target.name, { exact: false }),
      `${target.name} was drafted but appears in no pick list`,
    ).toBeVisible()

    // The clock advances, and it is no longer the user's turn — slot 1 does not pick twice in a row.
    await expect(page.getByText(/Round 1 · Pick 2/)).toBeVisible()
    await expect(
      page.getByText(/Your pick — choose a player below/),
      "the optimizer still thinks it is the user's turn after they used their pick",
    ).toHaveCount(0)

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("Undo returns the last pick to the board and rewinds the clock", async ({ page }) => {
    const { errors } = await startDraft(page)
    const target = (await availableRows(page))[0]

    await page.locator("table tbody tr").first().getByRole("button").click()
    await expect(page.getByText(/Round 1 · Pick 2/)).toBeVisible()

    await page.getByRole("button", { name: "Undo" }).click()

    // Both halves, because they fail independently: a rewind that restores the clock but not the
    // board leaves a player permanently missing from a two-hour draft.
    await expect
      .poll(async () => (await availableRows(page)).map((r) => r.id), {
        message: `Undo did not return ${target.name} to the board`,
      })
      .toContain(target.id)
    await expect(
      page.getByText(/Round 1 · Pick 1/),
      "Undo restored the player but left the clock on the next pick",
    ).toBeVisible()

    expectNoPageErrors(errors)
  })

  test("a mid-draft reload keeps the picks", async ({ page }) => {
    // ⭐ THE REASON THE STATE IS PERSISTED AT ALL. A draft runs for two hours in a tab that gets
    // reloaded, backgrounded and killed; losing the tracked picks at pick 40 is losing the session.
    // Nothing else in the suite reloads anything.
    const { errors } = await startDraft(page)
    const target = (await availableRows(page))[0]
    await page.locator("table tbody tr").first().getByRole("button").click()
    await expect(page.getByText(/Round 1 · Pick 2/)).toBeVisible()

    await page.reload()
    await page.getByRole("button", { name: "Start draft" }).click()
    await expect(page.locator("table tbody tr").first()).toBeVisible()

    await expect(
      page.getByText(/Round 1 · Pick 2/),
      "the tracked picks did not survive a reload — a two-hour session is one refresh from gone",
    ).toBeVisible()
    expect(
      (await availableRows(page)).map((r) => r.id),
      "the drafted player came back onto the board after a reload",
    ).not.toContain(target.id)

    expectNoPageErrors(errors)
  })
})

test.describe("finding a player on the board", () => {
  test("the Pts column sorts by points, and clicking again reverses it", async ({ page }) => {
    const { errors } = await startDraft(page)

    await page.getByRole("button", { name: /^Pts/ }).click()

    // ⚠️ K AND D/ST ARE DEFERRED TO THE BOTTOM BY DESIGN (`deferLowPred`) unless their own tab is
    // selected, so the ordering claim holds over the SKILL players — asserting over every row would
    // fail on a correct board and send the next reader at the sort code. Positions come from the
    // served payload rather than from the rendered badge.
    const pos = new Map((FIXTURES.boardFree() as any[]).map((p) => [p.id, p.pos]))
    const skillPts = (rows: Row[]) =>
      rows.filter((r) => !["K", "DST"].includes(pos.get(r.id) ?? "") && r.pts != null).map((r) => r.pts!)

    await expect
      .poll(
        async () => {
          const v = skillPts(await availableRows(page))
          return v.length > 1 && v.every((x, i) => i === 0 || v[i - 1] >= x)
        },
        { message: "sorting by Pts did not put the column in descending order" },
      )
      .toBe(true)

    // The toggle. A header that sorts one way and then does nothing is a control that looks live
    // and is not — and it is the natural bug, because the direction state is separate.
    await page.getByRole("button", { name: /^Pts/ }).click()
    await expect
      .poll(
        async () => {
          const v = skillPts(await availableRows(page))
          return v.length > 1 && v.every((x, i) => i === 0 || v[i - 1] <= x)
        },
        { message: "clicking Pts a second time did not reverse the sort" },
      )
      .toBe(true)

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("the position tabs and the search box both narrow the board", async ({ page }) => {
    const { errors } = await startDraft(page)
    const pos = new Map((FIXTURES.boardFree() as any[]).map((p) => [p.id, p.pos]))

    await page.getByRole("button", { name: "TE", exact: true }).click()
    await expect.poll(async () => (await availableRows(page)).length).toBeGreaterThan(0)

    const filtered = await availableRows(page)
    const wrong = filtered.filter((r) => pos.get(r.id) !== "TE")
    expect(
      wrong.slice(0, 5).map((r) => r.name),
      `the TE tab kept ${wrong.length} players who are not tight ends in the served board`,
    ).toEqual([])

    // Search composes with the filter rather than replacing it — the two are separate state and
    // an implementation that resets one on the other is a real, quiet annoyance mid-draft.
    const target = filtered[0]
    await page.getByPlaceholder("Search…").fill(target.name)
    await expect
      .poll(async () => (await availableRows(page)).map((r) => r.id), {
        message: `searching "${target.name}" inside the TE tab lost his row`,
      })
      .toContain(target.id)

    const searched = await availableRows(page)
    expect(
      searched.filter((r) => pos.get(r.id) !== "TE").slice(0, 5).map((r) => r.name),
      "searching inside a position tab escaped the filter",
    ).toEqual([])

    expectNoPageErrors(errors)
  })
})
