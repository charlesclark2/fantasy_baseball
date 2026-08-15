import { expect, test, type Page } from "@playwright/test"
import { collectPageErrors, FIXTURES, mockApi } from "../support/api-mock"
import { signIn } from "../support/session"
import { forbiddenPhrasesIn } from "../support/claim-denylist"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"

/**
 * E5.10 — /props SLATE NAVIGATION: group by game, search, sort, filter chips — on BOTH tabs.
 *
 * ══ WHAT ONLY A BROWSER CAN SEE HERE ═══════════════════════════════════════════════════════════
 *
 * Before this story `/props` was a flat card grid: a full MLB slate is 100+ quoted batters, so
 * finding a game, a batter, or comparing lines was a scroll problem. Every assertion below is about
 * BEHAVIOUR the payload alone cannot prove — the index endpoints already carry `game_pk`,
 * `team`/`opponent`, `game_datetime`, `batting_slot`, the line and the delta; whether the PAGE turns
 * that into a navigable slate is what this file is for.
 *
 * The fixture (`e2e/fixtures/build-props-slate.mjs`) is a synthetic 6-game, 108-batter / 12-pitcher
 * slate — six games so grouping/collapse/team-filter are real, dated in 2027 so "the next game to
 * start" is deterministic regardless of when the suite actually runs (every game is in the future).
 */

const TB = FIXTURES.propsTbSlate() as { batters: any[] }
const K = FIXTURES.propsKSlate() as { pitchers: any[] }

// The earliest-starting game in the fixture (MIA vs PIT, 17:10Z) — the one that must be expanded
// by default. game_pk 900006 (CHC vs STL) is the LATEST, used for the "jump to any game" case.
const FIRST_GAME_PK = 900001
const LAST_GAME_PK = 900006
const TB_BATTER_COUNT = TB.batters.filter((b: any) => b.game_pk === FIRST_GAME_PK).length
const K_PITCHER_COUNT = K.pitchers.filter((p: any) => p.game_pk === FIRST_GAME_PK).length

async function openProps(page: Page, opts: { tab?: "TB" | "K" } = {}) {
  const errors = collectPageErrors(page)
  await signIn(page, { groups: [] })
  const mock = await mockApi(page)
  await page.goto("/props")
  await expect(page.getByRole("heading", { name: "Props" })).toBeVisible()
  if (opts.tab === "TB") {
    await page.getByRole("button", { name: "Total Bases (TB)" }).click()
  }
  await expect(page.getByTestId("props-game-groups")).toBeVisible()
  return { errors, mock }
}

function gameGroup(page: Page, gamePk: number) {
  return page.locator(`[data-testid="props-game-group"][data-game-pk="${gamePk}"]`)
}

test.describe("games are grouped by matchup, collapsed except the next one to start", () => {
  for (const tab of ["TB", "K"] as const) {
    // ⭐ THE STRIKEOUTS TAB REGRESSION CHECK, PARAMETRIZED INSTEAD OF DUPLICATED. Both tabs go
    // through the exact same `frontend/lib/props-slate.ts` functions — running the same behaviour
    // clause against both is what proves that, rather than trusting that a fix applied to one
    // "probably" applies to the other.
    test(`[${tab}] six games render as six collapsible sections, and only the earliest is open`, async ({
      page,
    }) => {
      const { errors, mock } = await openProps(page, { tab })

      const groups = page.getByTestId("props-game-group")
      await expect(groups).toHaveCount(6)

      const first = gameGroup(page, FIRST_GAME_PK)
      await expect(first).toContainText("MIA vs PIT")
      const expectedCount = tab === "TB" ? TB_BATTER_COUNT : K_PITCHER_COUNT
      await expect(first).toContainText(`${expectedCount} ${tab === "TB" ? "batter" : "pitcher"}`)

      // The earliest game is expanded by default — its cards are already in the document.
      await expect(first.getByTestId("props-card")).toHaveCount(expectedCount)

      // ⚠️ Every OTHER game starts COLLAPSED — Radix Accordion content unmounts when closed, so
      // this is not "hidden with CSS", it is genuinely absent from the DOM. A default that rendered
      // every game expanded would pass a "the label is right" check and still leave a reader
      // scrolling past 100+ cards to find one game — the exact defect this story fixes.
      const last = gameGroup(page, LAST_GAME_PK)
      await expect(last.getByTestId("props-card")).toHaveCount(0)

      await expectNoNaN(page)
      await expectApiFullyMocked(mock)
      expectNoPageErrors(errors)
    })

    test(`[${tab}] tapping a collapsed game's header expands it`, async ({ page }) => {
      await openProps(page, { tab })
      const last = gameGroup(page, LAST_GAME_PK)
      await expect(last.getByTestId("props-card")).toHaveCount(0)

      await last.getByTestId("props-game-header").click()
      await expect(last.getByTestId("props-card").first()).toBeVisible()

      // …and clicking it again collapses it back — a real toggle, not a one-way reveal.
      await last.getByTestId("props-game-header").click()
      await expect(last.getByTestId("props-card")).toHaveCount(0)
    })
  }
})

test.describe("a 15-game slate is navigable to any game in ≤2 interactions", () => {
  test("a team filter chip jumps straight to that game, hiding every other one", async ({ page }) => {
    const { errors, mock } = await openProps(page, { tab: "TB" })

    // STL appears in exactly one game — the LATEST-starting one, which starts collapsed. ONE click
    // must both reveal it and remove the noise of the other five games — that is the mechanism that
    // makes "any game in ≤2 interactions" true regardless of slate size.
    await page.getByTestId("props-filter-team-STL").click()

    await expect(page.getByTestId("props-game-group")).toHaveCount(1)
    const game = gameGroup(page, LAST_GAME_PK)
    await expect(game).toBeVisible()
    await expect(game).toContainText("CHC vs STL")
    // …and it is EXPANDED, not merely the sole survivor of the filter — a filtered-to-one-and-still-
    // collapsed result would still cost the reader a second click.
    await expect(game.getByTestId("props-card").first()).toBeVisible()

    await expectNoNaN(page)
    await expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("clicking the chip again clears the filter and restores the full slate", async ({ page }) => {
    await openProps(page, { tab: "TB" })
    await page.getByTestId("props-filter-team-STL").click()
    await expect(page.getByTestId("props-game-group")).toHaveCount(1)

    await page.getByTestId("props-filter-team-STL").click()
    await expect(page.getByTestId("props-game-group")).toHaveCount(6)
  })
})

test.describe("name search finds a batter/pitcher by partial name", () => {
  test("[TB] a partial name narrows to that one player's game, and clearing restores the slate", async ({
    page,
  }) => {
    const { errors, mock } = await openProps(page, { tab: "TB" })

    // Partial, mixed-case — the story's own AC wording ("partial match").
    await page.getByTestId("props-search").fill("ohtANi")

    await expect(page.getByTestId("props-game-group")).toHaveCount(1)
    const cards = page.getByTestId("props-card")
    await expect(cards).toHaveCount(1)
    await expect(cards.first().getByTestId("props-card-name")).toHaveText("Shohei Ohtani")

    await page.getByTestId("props-search").fill("")
    await expect(page.getByTestId("props-game-group")).toHaveCount(6)

    await expectNoNaN(page)
    await expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("[K] a partial name finds a probable pitcher", async ({ page }) => {
    await openProps(page, { tab: "K" })
    await page.getByTestId("props-search").fill("valdez")
    const cards = page.getByTestId("props-card")
    await expect(cards).toHaveCount(1)
    await expect(cards.first().getByTestId("props-card-name")).toHaveText("Framber Valdez")
  })

  test("a search matching nobody says so, rather than rendering an empty grid", async ({ page }) => {
    const { mock } = await openProps(page, { tab: "TB" })
    await page.getByTestId("props-search").fill("zzz-nobody-on-this-slate")

    await expect(page.getByTestId("props-no-results")).toBeVisible()
    await expect(page.getByTestId("props-game-group")).toHaveCount(0)
    await expectApiFullyMocked(mock)
  })
})

test.describe("filter chips — line value and min book count", () => {
  test("a line-value chip leaves only rows carrying that exact line", async ({ page }) => {
    const { errors, mock } = await openProps(page, { tab: "TB" })
    await page.getByTestId("props-filter-line-1.5").click()

    // ⭐ THE ARITHMETIC CLAUSE. "Fewer cards" is satisfied by a filter keyed on the wrong field; every
    // surviving card's own rendered line must actually be 1.5.
    await expect
      .poll(async () => (await page.getByTestId("props-card").count()) > 0, {
        message: "the 1.5 line chip matched nothing — the fixture guarantees at least one row",
      })
      .toBe(true)
    const rawLines = await page
      .locator('[data-testid="props-card-line"]')
      .evaluateAll((els) => els.map((e) => e.getAttribute("data-line")))
    expect(
      rawLines.filter((v) => v !== "1.5"),
      "a card slipped through the 1.5 line filter with a different book line",
    ).toEqual([])

    // Toggling the same chip again clears it.
    await page.getByTestId("props-filter-line-1.5").click()
    await expect(page.getByTestId("props-game-group")).toHaveCount(6)

    await expectNoNaN(page)
    await expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("a min-book-count chip drops thinly-covered rows", async ({ page }) => {
    await openProps(page, { tab: "TB" })

    // ⚠️ `locator.count()` does NOT auto-retry — a single-shot read here would race the default
    // expand-state settling. Every game EXCEPT the default-expanded first one starts collapsed, so
    // click those five unconditionally rather than reading-then-deciding whether to click (the race
    // NF-C6P2 documents: a read that happens to land mid-render looks identical to "already open").
    for (const pk of [900002, 900003, 900004, 900005, 900006]) {
      await gameGroup(page, pk).getByTestId("props-game-header").click()
    }
    await expect
      .poll(() => page.getByTestId("props-card").count(), {
        message: "expanding every game did not grow the card count at all",
      })
      .toBeGreaterThan(TB_BATTER_COUNT)
    const fullSlate = await page.getByTestId("props-card").count()

    await page.getByTestId("props-filter-books-3").click()
    await expect
      .poll(() => page.getByTestId("props-card").count(), {
        message: "the 3+ books filter did not narrow the slate at all",
      })
      .toBeLessThan(fullSlate)
    await expect
      .poll(() => page.getByTestId("props-card").count())
      .toBeGreaterThan(0)
  })
})

test.describe("sort — Slate order stays the default, and every option is honestly labelled", () => {
  test("[TB] the sort control reads Slate order on first load", async ({ page }) => {
    await openProps(page, { tab: "TB" })
    await expect(page.getByLabel("Sort", { exact: true })).toContainText("Slate order")
    // The grouped view, not the flat list — the two are mutually exclusive render modes.
    await expect(page.getByTestId("props-game-groups")).toBeVisible()
    await expect(page.getByTestId("props-flat-list")).toHaveCount(0)
  })

  test("[K] the sort control reads Slate order on first load too", async ({ page }) => {
    await openProps(page, { tab: "K" })
    await expect(page.getByLabel("Sort", { exact: true })).toContainText("Slate order")
  })

  test("switching prop type resets the sort back to Slate order", async ({ page }) => {
    await openProps(page, { tab: "K" })
    await page.getByLabel("Sort", { exact: true }).click()
    await page.getByRole("option", { name: "Difference vs books", exact: true }).click()
    await expect(page.getByTestId("props-flat-list")).toBeVisible()

    await page.getByRole("button", { name: "Total Bases (TB)" }).click()
    await expect(page.getByLabel("Sort", { exact: true })).toContainText("Slate order")
    await expect(page.getByTestId("props-game-groups")).toBeVisible()
  })

  test("Proj TB sorts the flattened slate by projection, descending", async ({ page }) => {
    const { errors, mock } = await openProps(page, { tab: "TB" })
    await page.getByLabel("Sort", { exact: true }).click()
    await page.getByRole("option", { name: "Proj TB", exact: true }).click()

    await expect(page.getByTestId("props-flat-list")).toBeVisible()
    await expect(page.getByTestId("props-game-groups")).toHaveCount(0)

    const raw = await page.locator('[data-testid="props-card-proj"]').evaluateAll((els) =>
      els.map((e) => Number(e.getAttribute("data-proj"))),
    )
    expect(raw.length).toBeGreaterThan(0)
    const sorted = [...raw].sort((a, b) => b - a)
    expect(raw, "the flat list is not ordered by descending Proj TB").toEqual(sorted)

    await expectNoNaN(page)
    await expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("P(2+) sorts descending, and is offered on TB but not on K", async ({ page }) => {
    await openProps(page, { tab: "TB" })
    await page.getByLabel("Sort", { exact: true }).click()
    await expect(page.getByRole("option", { name: "P(2+)", exact: true })).toBeVisible()
    await page.getByRole("option", { name: "P(2+)", exact: true }).click()

    const raw = await page
      .locator('[data-testid="props-card-p2"]')
      .evaluateAll((els) => els.map((e) => Number(e.getAttribute("data-p2"))))
    const sorted = [...raw].sort((a, b) => b - a)
    expect(raw, "the flat list is not ordered by descending P(2+)").toEqual(sorted)

    // ⚠️ THE ISOLATING HALF. The K tab has no P(2+ bases) metric at all — a pitcher card never
    // renders one — so its sort menu must not offer a control for a number that does not exist.
    await openProps(page, { tab: "K" })
    await page.getByLabel("Sort", { exact: true }).click()
    await expect(page.getByRole("option", { name: "P(2+)", exact: true })).toHaveCount(0)
  })

  /**
   * ⭐⭐ THE PM RULING, PINNED. "Difference vs books" is a legitimate sort — the delta is
   * already-displayed transparency — but it must NEVER be the default and its label must never
   * drift toward editorial framing ("top plays", "best props", …). Two failure modes, both real
   * shipped shapes elsewhere in this repo (E2.1-r's inverted metric, the E7.14 over-eager-copy
   * class): a default that silently became the delta sort, and a rename that reads as a pick.
   */
  test("Difference vs books sorts by the already-displayed delta and is never the default", async ({
    page,
  }) => {
    const { errors, mock } = await openProps(page, { tab: "TB" })
    // Re-assert the default explicitly, in the SAME test as the honest-framing check below — a
    // regression that flips the default would be caught here even if a reader only reads this test.
    await expect(page.getByLabel("Sort", { exact: true })).toContainText("Slate order")

    await page.getByLabel("Sort", { exact: true }).click()
    await page.getByRole("option", { name: "Difference vs books", exact: true }).click()

    await expect(page.getByTestId("props-flat-list")).toBeVisible()
    const raw = await page
      .locator('[data-testid="props-card-diff"]')
      .evaluateAll((els) => els.map((e) => Number(e.getAttribute("data-diff"))))
    expect(raw.length).toBeGreaterThan(0)
    const sorted = [...raw].sort((a, b) => b - a)
    expect(raw, "the flat list is not ordered by descending difference-vs-books").toEqual(sorted)
    // The fixture deliberately spans both signs — proves the sort is a real numeric order, not a
    // filter that happened to keep the list in place.
    expect(raw.some((v) => v > 0) && raw.some((v) => v < 0), "the fixture has only one sign").toBe(true)

    // The shared denylist — "top", "best", "beats the market" etc. — screened against the WHOLE
    // rendered page, not just the sort menu, because a copy edit could put editorial language
    // anywhere (a section heading, an empty state) once this sort exists.
    const text = await page.evaluate(() => document.body.innerText)
    expect(forbiddenPhrasesIn(text), "an overclaim reached the props sort surface").toEqual([])

    await expectNoNaN(page)
    await expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })
})
