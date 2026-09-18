import { expect, test, type Page } from "@playwright/test"
import { collectPageErrors, mockApi, type MockOptions } from "../support/api-mock"
import { signIn } from "../support/session"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"
import served from "../fixtures/api/fantasy-nfl-waiver-pool.generated.json"

/**
 * NF-WVR1 Phase B — the waiver view on My Teams, asserted on RENDERED output (NF-C4: a guard on
 * source tests that someone typed a string). Every payload is the SHIPPING route's output over live
 * served data (`build-waiver-pool.py`), so assertions read the payload's OWN values, never a name.
 *
 * The properties, each a PM ruling:
 *   • opt-in — no roster re-read until the user opens the panel
 *   • ordering is WITHIN a position and by the stated realized basis only; the basis is visible
 *   • a blank is never a zero — defences and no-line players render "—" with their reason
 *   • no projection / value column; no recommendation language
 *   • every withheld state names its own cause
 *   • the renderer never reaches a free account
 */

const WAIVER_PATH = "/fantasy/nfl/waiver-pool"

async function openWaivers(
  page: Page,
  waiver: MockOptions["waiver"] = "served",
  extra: Partial<MockOptions> = {},
) {
  const errors = collectPageErrors(page)
  await signIn(page, { groups: ["subscriber"] })
  const mock = await mockApi(page, { entitlement: "entitled", leagues: "one", waiver, ...extra })
  await page.goto("/fantasy/my-teams")
  await expect(page.getByRole("heading", { name: "My Teams" })).toBeVisible()
  const panel = page.getByTestId("waiver-view").first()
  await expect(panel).toBeVisible()
  return { errors, mock, panel }
}

async function openPanel(
  page: Page,
  waiver: MockOptions["waiver"] = "served",
  extra: Partial<MockOptions> = {},
) {
  const ctx = await openWaivers(page, waiver, extra)
  await ctx.panel.getByTestId("waiver-toggle").click()
  return ctx
}

const waiverRequests = (requested: string[]) => requested.filter((r) => r.startsWith(WAIVER_PATH))

function num(text: string): number | null {
  const t = text.trim()
  return t === "—" ? null : Number(t)
}

test.describe("waiver view", () => {
  test("nothing is re-read until the panel is opened, and opening reads once", async ({ page }) => {
    const { mock, panel, errors } = await openWaivers(page)
    await page.waitForLoadState("networkidle")
    expect(waiverRequests(mock.requested), "the waiver pool was fetched on page load").toEqual([])
    await expect(panel.getByTestId("waiver-player")).toHaveCount(0)

    await panel.getByTestId("waiver-toggle").click()
    await expect(panel.getByTestId("waiver-player").first()).toBeVisible()
    await expect.poll(() => waiverRequests(mock.requested).length).toBe(1)
    expect(waiverRequests(mock.requested)[0]).toContain("refresh=true")
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("within the shown position, players are ordered by points so far and blanks come last", async ({
    page,
  }) => {
    const { panel } = await openPanel(page)
    // The default tab is the first position with an open starting slot — read from the payload.
    const open = served.need.positions.find((n) => n.need === "open_starter")!
    await expect(panel.getByTestId(`waiver-tab-${open.pos}`)).toHaveAttribute("aria-selected", "true")

    const group = served.pool!.find((g) => g.pos === open.pos)!
    const table = panel.getByTestId(`waiver-group-${open.pos}`)
    await panel.getByRole("button", { name: /Show all/ }).click()
    const cells = await table.getByTestId("waiver-points").allInnerTexts()
    expect(cells.length).toBe(group.players.length)

    const values = cells.map(num)
    const firstBlank = values.findIndex((v) => v === null)
    const numbers = (firstBlank === -1 ? values : values.slice(0, firstBlank)) as number[]
    expect(numbers.length, "the fixture must carry scored players or this clause is vacuous").toBeGreaterThan(1)
    for (let i = 1; i < numbers.length; i++) expect(numbers[i]).toBeLessThanOrEqual(numbers[i - 1])
    if (firstBlank !== -1) {
      expect(values.slice(firstBlank).every((v) => v === null), "a scored player sorted below a blank").toBe(true)
    }
    // …and the order is the server's, verbatim (the client never re-sorts).
    await expect(table.getByTestId("waiver-player").first()).toContainText(group.players[0].name)
  })

  test("the ordering basis and the covered weeks are stated on the surface", async ({ page }) => {
    const { panel } = await openPanel(page)
    await expect(panel.getByTestId("waiver-ordering-note")).toHaveText(served.ordering_note)
    await expect(panel.getByTestId("waiver-ordering-note")).toContainText("not a forecast")
    const weeks = served.realized!.weeks
    await expect(panel.getByTestId("waiver-coverage")).toContainText(
      weeks.length === 1 ? `week ${weeks[0]}` : `weeks ${weeks[0]}`,
    )
    // The league scores a term the realized line cannot supply — the payload says so, and so must we.
    expect(served.realized!.captured_terms.length).toBeGreaterThan(0)
    await expect(panel.getByTestId("waiver-coverage")).toContainText("don't include")
    await expect(panel.getByTestId("waiver-freshness")).toContainText("Rosters read from your league at")
  })

  test("a team defence is a stated absence, never a zero", async ({ page }) => {
    const { panel } = await openPanel(page)
    await panel.getByTestId("waiver-tab-DST").click()
    const table = panel.getByTestId("waiver-group-DST")
    await expect(table.getByTestId("waiver-group-absence")).toContainText("team-defence results")
    const cells = await table.getByTestId("waiver-points").allInnerTexts()
    expect(cells.length).toBeGreaterThan(0)
    expect(cells.every((c) => c.trim() === "—"), `a defence rendered a number: ${cells}`).toBe(true)
  })

  test("a player with no stat line shows a blank and why, not a zero", async ({ page }) => {
    const { panel } = await openPanel(page)
    const group = served.pool!.find((g) =>
      g.players.some((p) => p.realized?.absence === "no_realized_line") && g.pos !== "DST",
    )!
    await panel.getByTestId(`waiver-tab-${group.pos}`).click()
    const table = panel.getByTestId(`waiver-group-${group.pos}`)
    const more = panel.getByRole("button", { name: /Show all/ })
    if (await more.count()) await more.click()
    const blank = group.players.find((p) => p.realized?.absence === "no_realized_line")!
    const row = table.getByTestId("waiver-player").filter({ hasText: blank.name }).first()
    await expect(row.getByTestId("waiver-points")).toHaveText("—")
    await expect(row.getByTestId("waiver-player-absence")).toContainText("No stat line")
  })

  test("there is no projection or value column", async ({ page }) => {
    const { panel } = await openPanel(page)
    const headers = await panel.locator("thead th").allInnerTexts()
    expect(headers.length).toBe(3)
    expect(headers.join(" ")).not.toMatch(/proj|value|vor|rank|forecast/i)
    await expect(panel.getByText(/projected/i)).toHaveCount(0)
  })

  test("a week RC1 left out of the totals is named, not silently missing", async ({ page }) => {
    const { panel } = await openPanel(page, "excluded")
    await expect(panel.getByTestId("waiver-coverage")).toContainText(
      "Not included in these totals yet: week 2 (still in progress)",
    )
  })

  test("a truncated league withholds the list and says why", async ({ page }) => {
    const { panel } = await openPanel(page, "refused")
    // The TRUNCATION-specific sentence, not merely "already taken" — the generic fallback says that
    // too, and a refusal that stops naming its own cause is the NF-C6b defect.
    await expect(panel.getByTestId("waiver-refusal")).toContainText("more rostered players than we store")
    await expect(panel.getByTestId("waiver-player")).toHaveCount(0)
    // The need annotation still renders — it does not depend on the other rosters.
    await expect(panel.getByTestId("waiver-need")).toBeVisible()
  })

  test("with no published weeks the list is explicitly unordered and shows no points", async ({ page }) => {
    const { panel } = await openPanel(page, "unpublished")
    await expect(panel.getByTestId("waiver-facts-absence")).toContainText("no particular order")
    await expect(panel.getByTestId("waiver-ordering-note")).toContainText("NOT ranked")
    await expect(panel.getByTestId("waiver-player").first()).toBeVisible()
    const cells = await panel.getByTestId("waiver-points").allInnerTexts()
    expect(cells.every((c) => c.trim() === "—")).toBe(true)
    await expect(panel.getByText("Points so far")).toHaveCount(0)
  })

  test("an un-refreshable platform says the list is as old as the import", async ({ page }) => {
    const { panel } = await openPanel(page, "espn")
    await expect(panel.getByTestId("waiver-freshness")).toContainText("Re-import the league")
    await expect(panel.getByTestId("waiver-player").first()).toBeVisible()
  })

  test("a league the server will not serve shows the server's own sentence", async ({ page }) => {
    const { panel } = await openPanel(page, "notFound")
    await expect(panel.getByTestId("waiver-error")).toHaveText("League not found")
  })

  test("the copy makes no pickup claim and no forecast", async ({ page }) => {
    const { panel, errors } = await openPanel(page)
    await expect(panel.getByTestId("waiver-player").first()).toBeVisible()
    const text = await panel.innerText()
    expect(forbiddenPhrasesIn(text)).toEqual([])
    expect(text).not.toMatch(/\b(pick ?ups?|must[- ]add|you should|will score|breakout|top adds?)\b/i)
    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("on a phone the list fits without scrolling sideways — page or table", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 })
    const { panel } = await openPanel(page)
    await expect(panel.getByTestId("waiver-player").first()).toBeVisible()
    const pageOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(pageOverflow).toBeLessThanOrEqual(0)
    // ⚠️ The page-level check cannot see a table scrolling inside its OWN container (NF-C6b), so the
    // scrolling container itself is measured too.
    const inner = await panel.locator(".overflow-x-auto").evaluateAll((els) =>
      els.map((e) => e.scrollWidth - e.clientWidth),
    )
    expect(inner.length).toBeGreaterThan(0)
    expect(Math.max(...inner)).toBeLessThanOrEqual(0)
  })

  test("each available player links to his page in a new tab", async ({ page }) => {
    const { panel } = await openPanel(page)
    const group = served.pool!.find((g) => g.pos === served.need.positions.find((n) => n.need === "open_starter")!.pos)!
    const link = panel.getByTestId("waiver-player-link").first()
    await expect(link).toHaveText(group.players[0].name)
    await expect(link).toHaveAttribute("href", `/fantasy/player/${group.players[0].id}`)
    await expect(link).toHaveAttribute("target", "_blank")
    await expect(link).toHaveAttribute("rel", /noopener/)
  })

  test("an IR count is shown beside the need and not counted as held", async ({ page }) => {
    const { panel } = await openPanel(page, "served", {
      transform: (path, body) => {
        if (path !== "/fantasy/nfl/waiver-pool") return body
        const wr = body.need.positions.find((n: { pos: string }) => n.pos === "WR")
        wr.reserved = 1
        return body
      },
    })
    await expect(panel.getByTestId("waiver-need-WR")).toContainText("1 on IR/taxi (not counted)")
  })

  // ⑰ (PM ruling 2026-09-18) — the alias detector's refusal must NAME the pair. "A name didn't
  // match" with no name in it sends the reader nowhere, and the generic fallback would satisfy a
  // weaker assertion, so this checks BOTH sides' spellings are on screen.
  test("the alias refusal withholds the list and names both spellings", async ({ page }) => {
    const { panel } = await openPanel(page, "aliasRefused")
    await expect(panel.getByTestId("waiver-refusal")).toBeVisible()
    await expect(panel.getByTestId("waiver-refusal")).toContainText("spelled differently")
    const note = panel.getByTestId("waiver-alias-note")
    await expect(note).toBeVisible()
    await expect(note).toContainText("Josh Palmer")
    await expect(note).toContainText("Joshua Palmer")
    // The pool is withheld, so no player table renders at all.
    await expect(panel.getByTestId("waiver-row")).toHaveCount(0)
  })

  // ㉜ = (b) (PM ruling 2026-09-18) — name the uncovered scoring terms, grouped.
  test("the uncovered scoring terms are named, grouped, beside the columns", async ({ page }) => {
    const { panel } = await openPanel(page, "capturedTerms")
    const block = panel.getByTestId("waiver-captured-terms")
    await expect(block).toBeVisible()
    // Collapsed: the summary counts them by group rather than listing 9 keys inline.
    await expect(block).toContainText("Kicking (4)")
    await expect(block).toContainText("Defense (4)")
    await expect(block).toContainText("Other (1)")
    await block.locator("summary").click()
    // Expanded: the catalog's own LABELS, not the raw keys, for every term the catalog carries…
    await expect(block).toContainText("FG made 50-59")
    await expect(block).toContainText("Blocked kick")
    await expect(block).toContainText("Points allowed 0")
    // …and a platform-specific key the catalog does NOT carry is still listed (never dropped),
    // grouped by its prefix rather than filed under "Other".
    await expect(block).toContainText("fgm_55p")
    const kicking = await block.locator("li").filter({ hasText: "Kicking:" }).innerText()
    expect(kicking, "an unknown fg key must group as Kicking, not Other").toContain("fgm_55p")
    // ⛔ And it must not claim a size for the gap: a captured term has no source, so there is
    // nothing to sum (the ㉜ constraint).
    const text = await block.innerText()
    expect(text).not.toMatch(/\b\d+(\.\d+)?\s*(points|pts)\b/i)
  })

  test("the waiver view never reaches a free account", async ({ page }) => {
    await signIn(page, { groups: [] })
    const mock = await mockApi(page, { entitlement: "free", leagues: "one" })
    await page.goto("/fantasy/my-teams")
    await page.waitForURL((url) => !url.pathname.startsWith("/fantasy/my-teams"), { timeout: 10_000 })
    expect(new URL(page.url()).pathname).toBe("/subscribe")
    await expect(page.getByTestId("waiver-view")).toHaveCount(0)
    expect(waiverRequests(mock.requested)).toEqual([])
  })
})


test.describe("injured reserve on My Teams", () => {
  // The `drafted` league with ONE bench row re-flagged `slot: "ir"` — the shape the waiver refresh
  // (and a fresh import) now writes. Read from the served payload, never a hardcoded name.
  const markIr = (path: string, body: any) => {
    if (path !== "/fantasy/nfl/my-teams") return body
    for (const rows of Object.values(body.rosters ?? {}) as any[]) {
      const bench = rows.find((r: any) => !r.roster.starter)
      if (bench) bench.roster.slot = "ir"
    }
    return body
  }

  test("an IR player is listed under Injured reserve, not Bench", async ({ page }) => {
    let irName = ""
    await signIn(page, { groups: ["subscriber"] })
    await mockApi(page, {
      entitlement: "entitled",
      leagues: "drafted",
      transform: (path, body) => {
        const out = markIr(path, body)
        if (path === "/fantasy/nfl/my-teams") {
          const rows = Object.values(out.rosters ?? {})[0] as any[]
          irName = rows.find((r: any) => r.roster.slot === "ir")?.roster.name ?? ""
        }
        return out
      },
    })
    await page.goto("/fantasy/my-teams")
    const ir = page.getByTestId("ir-table")
    await expect(ir).toBeVisible()
    expect(irName, "the fixture must carry a bench row to re-flag").not.toBe("")
    await expect(ir).toContainText(irName)
    await expect(page.getByTestId("bench-table")).not.toContainText(irName)
  })

  test("opening the waiver panel re-reads My Teams when it rewrote the saved roster", async ({ page }) => {
    const { mock, panel } = await openWaivers(page, "ownRefreshed")
    const myTeams = () => mock.requested.filter((r) => r.startsWith("/fantasy/nfl/my-teams")).length
    await page.waitForLoadState("networkidle")
    const before = myTeams()
    await panel.getByTestId("waiver-toggle").click()
    await expect(panel.getByTestId("waiver-player").first()).toBeVisible()
    await expect.poll(myTeams).toBeGreaterThan(before)
  })

  test("a refresh that did not touch the saved roster does not re-read My Teams", async ({ page }) => {
    const { mock, panel } = await openWaivers(page, "served")
    const myTeams = () => mock.requested.filter((r) => r.startsWith("/fantasy/nfl/my-teams")).length
    await page.waitForLoadState("networkidle")
    const before = myTeams()
    await panel.getByTestId("waiver-toggle").click()
    await expect(panel.getByTestId("waiver-player").first()).toBeVisible()
    await page.waitForLoadState("networkidle")
    expect(myTeams()).toBe(before)
  })
})
