import { expect, test, type Page } from "@playwright/test"
import { FIXTURES, mockApi, collectPageErrors, type MockOptions } from "../support/api-mock"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"

/**
 * NF-RATE1 — THE FULL-SEASON RATE IS NOT PRINTED WHEN IT IS ABOVE ANY FULL SEASON ON RECORD.
 *
 * THE DEFECT (measured on the staged 2026 board). `pts × 17 ÷ g` on a heavily availability-capped
 * row prints a rate above every real player on the board — GEORGE KITTLE 580, ALEC PIERCE 545, and
 * WILL LEVIS 633 — against a #1 overall at 414. `MIN_GAMES_FOR_FULL_SEASON_RATE` does not catch
 * them: all three sit at 3.3–3.7 expected games, comfortably above the floor. The floor guards the
 * DENOMINATOR'S RESOLUTION; this is a defect in the RATIO, and it needed its own anchor.
 *
 * ⭐ WHY THIS NEEDS A BROWSER, given `test_nf_rate1_full_season_rate_suppression.py` exists. That
 * suite proves the RULE is right, single-owned and derived. None of that is a property a reader
 * has, and all of it is satisfied by a page that renders the wrong thing:
 *
 *   1. THE WITHHELD CELL MUST BE DISTINGUISHABLE FROM AN EMPTY ONE. The pre-existing `unavailable`
 *      state already renders a bare em-dash, so a build that computed `withheld` and then rendered
 *      it identically would convert "we are not printing this" into "we have nothing for this
 *      player" — the E9.56c inversion, and invisible to `tsc`, `next build` and every source scan.
 *   2. IT MUST FIRE ON THE VIOLATING ROW AND ONLY THAT ROW. A treatment on every row is decoration;
 *      one on none is indistinguishable from the defect. Only the PAIR is the test, which is why
 *      every case below plants one row and names an untouched control beside it.
 *   3. ⭐⭐ THE FOURTH SITE IS A DOWNLOADED FILE. `rankings-board.tsx` renders the rate TWICE — the
 *      on-page column and the CSV export's `full_season_rate` — and NF-INJ3b's follow-up named the
 *      export specifically as the surface a table-only fix silently misses. No DOM assertion can
 *      see it; the CSV case below reads the actual downloaded bytes.
 *   4. THE TWO NUMBERS BESIDE IT MUST SURVIVE. Ruling D3 keeps `pts` and `g` served, so the reader
 *      can still divide. A build that blanked the row would be a withholding, not a render fix.
 *
 * ⛔⛔ THE FIXTURE IS PLANTED, AND IT HAS TO BE. The committed 858-row board fixture is a pre-flip
 * vintage in which NOT ONE row breaches the envelope (measured), so asserting against it as-is
 * would assert nothing at all. `transform` is the harness's sanctioned way to model a served state
 * we cannot capture — and the plant reproduces the real defect's SHAPE rather than an arbitrary
 * one: the point total is left EXACTLY where the fixture has it and only the games figure is cut,
 * which is precisely how NF1.5's re-order produces these rows (`_RAW_SCALE_COLS` rescales the stat
 * columns and not `proj_games`).
 */

/** The planted row and its control, both named rather than positional, both reached through the
 *  search box by NAME — which is what a reader does (NF-C9's id-normalisation lesson).
 *
 *  `WITHHELD.games` is ABOVE `MIN_GAMES_FOR_FULL_SEASON_RATE`, deliberately: a plant below the
 *  floor would be refused by the PRE-EXISTING guard and every clause here would pass without the
 *  new rule existing at all — the vacuous-fixture shape (NF-INJ2b), and the one this story is most
 *  exposed to because the two refusals render so similarly.
 *
 *  `CLEAN` is a WR carrying a perfectly ordinary 16-game line whose rate (~268) sits well inside the
 *  435.2 a real WR season has posted, so he must still print a number. */
const WITHHELD = { name: "Jaxon Smith-Njigba", id: "00-0038543", pts: 138.3, games: 3.7 }
const CLEAN = { name: "Puka Nacua", id: "00-0039075" }

/** ~635 at 3.7 games — above the 435.2 ceiling, and above every number on the board. */
const WITHHELD_RATE = Math.round((WITHHELD.pts * 17) / WITHHELD.games)

/** The disclosure's trigger, located by its ACCESSIBLE NAME — the only thing on it that carries
 *  meaning, since the visible label is an em-dash a screen reader announces as nothing at all.
 *  Mirrors `FULL_SEASON_RATE_WITHHELD_SR_LABEL`. */
const WITHHELD_TRIGGER = /full-season rate withheld/i

/**
 * Cut the planted player's expected games on BOTH payloads, leaving his points untouched.
 *
 * ⚠️ BOTH, and that is not belt-and-braces: `/fantasy/nfl/board` feeds the rankings board and its
 * CSV, `/fantasy/nfl/projections` feeds the projections table — and the PLAYER PAGE reads BOTH at
 * once, printing a rate off each. A plant on one endpoint would leave one of the page's two tiles
 * quietly un-tested, which is exactly the "four sites, not one" defect in miniature.
 */
function withCappedGames(extra?: Partial<MockOptions>): MockOptions {
  const cap = (p: any) => (p?.id === WITHHELD.id ? { ...p, g: WITHHELD.games, pts: WITHHELD.pts, fpPpr: WITHHELD.pts } : p)
  return {
    ...extra,
    transform: (pathname, body) => {
      const next = extra?.transform ? extra.transform(pathname, body) : body
      if (pathname === "/fantasy/nfl/board" && Array.isArray(next)) return next.map(cap)
      if (pathname === "/fantasy/nfl/projections" && Array.isArray(next?.players)) {
        return { ...next, players: next.players.map(cap) }
      }
      return next
    },
  }
}

/** Both boards paginate and sort, so a named row is reached through the search box. */
async function rowFor(page: Page, playerName: string) {
  await page.getByPlaceholder("Search player").fill(playerName)
  const row = page.locator("table tbody tr", { hasText: playerName }).first()
  await expect(row).toBeVisible()
  return row
}

async function openBoard(page: Page, path: string) {
  await page.goto(path)
  // ⚠️ Wait for FETCHED content. A snapshot taken straight after `goto` can capture the loading
  // state, in which every row is legitimately absent — and the spec then reports a product defect
  // for its own race (the CI-only flake NF-TR1 had to fix).
  await expect(page.locator("table tbody tr").first()).toBeVisible()
}

test.describe("the rankings board — the on-page column", () => {
  test("the absurd row is withheld, the ordinary row still prints its rate", async ({ page }) => {
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, withCappedGames())
    await openBoard(page, "/fantasy/rankings")

    const withheld = await rowFor(page, WITHHELD.name)
    await expect(
      withheld.getByRole("button", { name: WITHHELD_TRIGGER }),
      `${WITHHELD.name} implies a ${WITHHELD_RATE}-point full season — above any real WR season — ` +
        `and the board renders no withheld disclosure, so the cell reads as "we have nothing for ` +
        `this player" rather than as a refusal`,
    ).toBeVisible()

    // ⛔ AND THE NUMBER ITSELF IS GONE. "a disclosure rendered" alone is satisfied by a build that
    // prints 635 with a tooltip beside it, which is strictly worse than the defect.
    expect(
      await withheld.innerText(),
      `the absurd rate still renders on the withheld row`,
    ).not.toContain(String(WITHHELD_RATE))

    // ⭐ RULING D3: pts and g both STAY SERVED and both still render. This is a render fix, not a
    // withholding — the reader can still take the quotient themselves.
    const text = await withheld.innerText()
    expect(text, "the projected-points figure vanished from the withheld row").toContain("138.3")
    expect(text, "the expected-games figure vanished from the withheld row").toContain("3.7")

    const clean = await rowFor(page, CLEAN.name)
    await expect(
      clean.getByRole("button", { name: WITHHELD_TRIGGER }),
      `${CLEAN.name}'s rate is inside what a real WR season has posted and it was withheld anyway ` +
        `— a suppression one row too wide costs a reader a number that was fine`,
    ).toHaveCount(0)
    await expect(
      clean.locator("td", { hasText: /^\s*[\d,]+\.\d+\s*$/ }).first(),
      `${CLEAN.name}'s row no longer renders numbers at all`,
    ).toBeVisible()

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("the disclosure opens and refuses every forecast reading", async ({ page }) => {
    // ⭐ THE CLAUSE A SOURCE SCAN CANNOT MAKE. The wording is screened in `fantasy-claim-copy.ts`,
    // but only a rendered read proves the copy the reader actually meets is that wording — and the
    // denylist runs over what the BROWSER shows, which includes every static string a component
    // contributes.
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, withCappedGames())
    await openBoard(page, "/fantasy/rankings")

    const withheld = await rowFor(page, WITHHELD.name)
    await withheld.getByRole("button", { name: WITHHELD_TRIGGER }).first().click()

    const disclosure = page.getByText(/higher than any full season on record/i).first()
    await expect(
      disclosure,
      "the withheld cell's disclosure does not open, so the refusal is unexplainable",
    ).toBeVisible()

    const body = await page.locator("body").innerText()
    expect(forbiddenPhrasesIn(body), "the withheld disclosure carries an overclaim").toEqual([])
    // ⛔ NO FORECAST AND NO INJURY CLAIM. This column is not about availability at all, so an
    // availability verb here would be both unearned and wrong.
    for (const banned of [/expected to miss/i, /will miss/i, /is injured/i, /injury/i]) {
      expect(body, `the withheld disclosure makes a forecast: ${banned}`).not.toMatch(banned)
    }

    expectNoPageErrors(errors)
    expectApiFullyMocked(mock)
  })
})

test.describe("the CSV export — the site a table-only fix misses", () => {
  test("full_season_rate is EMPTY on the withheld row and a number on the clean one", async ({
    page,
  }) => {
    // ⭐⭐ THE FOURTH RENDER SITE, and the only one that leaves the page. A spreadsheet reader has
    // no tooltip, so the only honest renderings are a value or nothing — a sentinel string would
    // break the column's type for anyone who sorts or averages it, and `0`/`-1` would be a wrong
    // number rather than an absent one.
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, withCappedGames())
    await openBoard(page, "/fantasy/rankings")

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Export CSV" }).click(),
    ])
    const stream = await download.createReadStream()
    const chunks: Buffer[] = []
    for await (const chunk of stream) chunks.push(Buffer.from(chunk))
    const csv = Buffer.concat(chunks).toString("utf8")

    const lines = csv.trim().split("\n")
    const header = lines[0].split(",")
    const iRate = header.indexOf("full_season_rate")
    const iName = header.indexOf("player")
    const iPts = header.indexOf("expected_pts")
    const iGames = header.indexOf("expected_games")
    expect(iRate, "the export no longer carries a full_season_rate column").toBeGreaterThan(-1)

    const cellsFor = (name: string) => {
      const line = lines.find((l) => l.includes(name))
      expect(line, `${name} is missing from the exported file`).toBeTruthy()
      return line!.split(",")
    }

    const withheldCells = cellsFor(WITHHELD.name)
    expect(
      withheldCells[iRate],
      `the exported full_season_rate for ${WITHHELD.name} is "${withheldCells[iRate]}" — the ` +
        `on-page column withholds this row, so an export that still carries the number ships the ` +
        `absurd figure in a machine-readable file`,
    ).toBe("")
    // ⭐ EMPTY IN *THIS* COLUMN ONLY. A build that dropped the whole row, or blanked its
    // neighbours, would also produce an empty rate cell — and would be a withholding, not a render
    // fix. Ruling D3 keeps both inputs in the file.
    expect(withheldCells[iPts], "expected_pts was blanked on the withheld row").not.toBe("")
    expect(withheldCells[iGames], "expected_games was blanked on the withheld row").not.toBe("")

    const cleanCells = cellsFor(CLEAN.name)
    expect(
      cleanCells[iRate],
      `${CLEAN.name}'s rate is inside the realized envelope and the export blanked it anyway — a ` +
        `column emptied for everyone passes a "suppressed rows are empty" check and is useless`,
    ).not.toBe("")
    expect(Number(cleanCells[iRate])).toBeGreaterThan(0)
    expect(cleanCells[iName]).toContain(CLEAN.name)

    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })
})

test.describe("the projections table — the other public board", () => {
  test("the absurd row is withheld and the ordinary row is untouched", async ({ page }) => {
    // NOT REDUNDANT with the rankings case: a DIFFERENT component reading a DIFFERENT endpoint,
    // with its own scoring picker. This repo's recurring shape is a fix landing on one of the two
    // public boards and not the other (#681 locked the board's format picker and left this one open
    // for the whole of that PR's life).
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, withCappedGames())
    await openBoard(page, "/fantasy/projections")

    const withheld = await rowFor(page, WITHHELD.name)
    await expect(
      withheld.getByRole("button", { name: WITHHELD_TRIGGER }),
      `the projections table prints a full-season rate the rankings board withholds`,
    ).toBeVisible()
    expect(await withheld.innerText()).not.toContain(String(WITHHELD_RATE))

    const clean = await rowFor(page, CLEAN.name)
    await expect(
      clean.getByRole("button", { name: WITHHELD_TRIGGER }),
      `${CLEAN.name} was withheld on the projections table`,
    ).toHaveCount(0)

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })
})

test.describe("the player page — two tiles, two call sites", () => {
  test("the withheld rate is a STATED absence, not a missing line", async ({ page }) => {
    // ⭐ THE ONE SURFACE WHERE THE THREE STATES RENDER DIFFERENTLY, and deliberately so. A rate
    // that cannot be computed is simply ABSENT from the tile's sub-line (a sub-line is a list of
    // present facts, and that is the pre-story behaviour this story leaves alone). A rate we are
    // REFUSING to print renders as a stated absence with the disclosure behind it, because
    // "we have this number and are not printing it" is a fact an omitted line cannot state.
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, withCappedGames())

    await page.goto(`/fantasy/player/${WITHHELD.id}`)
    await expect(page.getByRole("heading", { name: WITHHELD.name })).toBeVisible()
    await expect(page.getByTestId("format-tile-ppr")).toBeVisible()

    const tile = await page.getByTestId("format-tile-ppr").innerText()
    expect(tile, "the player page prints the absurd rate the two boards withhold").not.toContain(
      String(WITHHELD_RATE),
    )
    await expect(
      page.getByRole("button", { name: WITHHELD_TRIGGER }).first(),
      "the withheld rate is simply missing from the tile — a reader cannot tell a refusal from a " +
        "gap, which is the one thing this must never look like",
    ).toBeVisible()
    // The total the rate is derived FROM is untouched (ruling D3).
    expect(tile, "the Full-PPR total vanished with the rate").toContain("138.3")

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("an ordinary player's tiles still carry the rate", async ({ page }) => {
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, withCappedGames())
    const proj = (FIXTURES.projectionsEntitled().players as any[]).find((p) => p.id === CLEAN.id)
    expect(proj, "fixture assumption: the control player is in the projections payload").toBeTruthy()

    await page.goto(`/fantasy/player/${CLEAN.id}`)
    await expect(page.getByTestId("format-tile-ppr")).toBeVisible()

    const tile = await page.getByTestId("format-tile-ppr").innerText()
    expect(tile, "the control player's tile lost its full-season-rate line").toContain(
      "Full-season rate:",
    )
    // Pin the arithmetic against the fixture the page fetched — the rule must not perturb a value
    // it lets through.
    const rendered = tile.match(/Full-season rate:\s*([\d,.]+)/)?.[1]
    expect(rendered, `no rate value in "${tile}"`).toBeTruthy()
    expect(Number(rendered!.replace(/,/g, ""))).toBeCloseTo((proj.fpPpr * 17) / proj.g, 1)
    await expect(page.getByRole("button", { name: WITHHELD_TRIGGER })).toHaveCount(0)

    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })
})
