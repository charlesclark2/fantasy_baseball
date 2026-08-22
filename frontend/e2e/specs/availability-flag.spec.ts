import { expect, test, type Page } from "@playwright/test"
import { collectPageErrors, mockApi, type MockOptions } from "../support/api-mock"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"

/**
 * NF-C8 — THE AVAILABILITY FLAG, at the render level.
 *
 * THE DEFECT. The projection already multiplies the chance a player misses games through his point
 * total, and `g` is served beside it — so on every board the discount is PRESENT and INVISIBLE. A
 * drafter meets a player ranked two rounds lower than he expected and a points number he cannot
 * account for; the column that explains it is four columns right, in the same grey as everything
 * else. The flag colours the games figure on the rows where the discount is material.
 *
 * ⭐ WHY THIS NEEDS A BROWSER. `betting_ml/tests/test_nf_c8_availability_flag_copy.py` proves the
 * COPY is honest and that all three surfaces BIND the component. Neither is the property a reader
 * has, and both are satisfiable by a page that never renders one:
 *
 *   1. THE FLAG MUST APPEAR ON THE RIGHT ROWS AND ONLY THOSE. A classifier is one `<` from
 *      flagging the whole board (which is decoration, not disclosure) or none of it (which is
 *      indistinguishable from the defect it fixes). Both are green in `tsc`.
 *   2. THE DEFINITION MUST OPEN ON TAP. `InfoTip` is Popover-based precisely because a Radix
 *      Tooltip closes on pointerdown and can never be opened by a touch. A source scan sees
 *      `<InfoTip>` either way; only a real tap on a hover-less viewport tells them apart — see the
 *      `mobile` project in `playwright.config.ts`, which this spec is registered in.
 *
 * ⛔⛔ THE FIXTURE IS PLANTED, AND IT HAS TO BE. The captured board serves `g` as integers 14–17
 * (measured: 858 rows, min 14 apart from three deliberately-degenerate rows), so NOTHING on it
 * flags. Asserted against that fixture, "no badge on a full-season row" would pass on a board where
 * the feature does not exist, and "a badge on a low-g row" would have no row to run on — the
 * NF-C4/NF-C6P3 lesson that a fixture which cannot distinguish the correct implementation from the
 * broken one tests neither. So `withGames` plants four rows spanning both tiers, the exclusive
 * boundary, and a full season.
 */

/** The four planted rows. Ids are stable across the board AND projections fixtures (checked), so
 *  the same players drive the player page. */
const HEAVILY_LIMITED = { name: "Jonathan Taylor", id: "00-0036223", g: 7.3, shown: "7.3" }
const LIMITED = { name: "Justin Jefferson", id: "00-0036322", g: 11.5, shown: "11.5" }
/** ⭐ EXACTLY AT THE THRESHOLD. `LIMITED_AVAILABILITY_GAMES` is 12.5 and the comparison is strictly
 *  `<`, so this row must NOT flag — the single most likely off-by-one in the whole story, and one
 *  no other row in the fixture can see.
 *
 *  ⚠️ ALSO THE ROW THAT KEEPS THE THRESHOLD HONEST. It was 14 until the served distribution was
 *  measured (the median draftable skill player is 14.4, so a 14-game threshold flagged 37.6% of
 *  them). If this constant is ever edited to make a real player flag or stop flagging rather than
 *  to track `LIMITED_AVAILABILITY_GAMES`, the fixture has stopped testing the boundary and started
 *  encoding an opinion. */
const AT_THRESHOLD = { name: "Derrick Henry", id: "00-0032764", g: 12.5 }
/** Untouched by the transform: a genuine full-season row, proving the flag is not painted on
 *  everything. */
const FULL_SEASON = { name: "Zay Jones", id: "00-0033891" }

const PLANTED: Record<string, number> = {
  [HEAVILY_LIMITED.id]: HEAVILY_LIMITED.g,
  [LIMITED.id]: LIMITED.g,
  [AT_THRESHOLD.id]: AT_THRESHOLD.g,
}

/** The flag's rendered trigger. Located by its ACCESSIBLE NAME rather than by a class or a colour:
 *  the accessible name is what a screen reader gets and what a colour-blind reader depends on, so
 *  asserting on it covers the disclosure rather than the decoration. */
const FLAG = /limited projected availability/i

/**
 * Plant the expected-games values on every payload that carries them.
 *
 * ⚠️ ALL FOUR PATHS, not just the board. `projections-table` reads `projections-full` when it can
 * and falls back to `projections`; the player page joins the projections blob to the board. A
 * transform that covered only one of them would leave a surface silently testing the un-planted
 * fixture — i.e. passing because nothing flags there either.
 */
function withGames(extra?: Partial<MockOptions>): MockOptions {
  return {
    ...extra,
    transform: (pathname, body) => {
      const patch = (p: any) => (p?.id in PLANTED ? { ...p, g: PLANTED[p.id] } : p)
      if (pathname === "/fantasy/nfl/board" && Array.isArray(body)) return body.map(patch)
      if (pathname.startsWith("/fantasy/nfl/projections") && Array.isArray(body?.players)) {
        return { ...body, players: body.players.map(patch) }
      }
      return extra?.transform ? extra.transform(pathname, body) : body
    },
  }
}

/** The board/projections tables paginate and sort, so a named row is reached through the search
 *  box rather than by index (the `freemium-board.spec.ts` pattern). */
async function rowFor(page: Page, playerName: string) {
  await page.getByPlaceholder("Search player").fill(playerName)
  const row = page.locator("table tbody tr", { hasText: playerName }).first()
  await expect(row).toBeVisible()
  return row
}

async function gotoTable(page: Page, path: string) {
  await page.goto(path)
  // ⚠️ Wait for FETCHED content before reading the page — a snapshot taken straight after `goto`
  // can capture the loading state, in which every row is legitimately absent, and the spec then
  // reports a product defect for its own race (the CI-only flake NF-TR1 had to fix).
  await expect(page.locator("table tbody tr").first()).toBeVisible()
}

test.describe("the availability flag — which rows carry it", () => {
  for (const [surface, path] of [
    ["Rankings", "/fantasy/rankings"],
    ["Projections", "/fantasy/projections"],
  ] as const) {
    test(`${surface}: a materially-low games row is flagged and a full-season row is not`, async ({
      page,
    }) => {
      // ⭐ THE PAIR IS THE TEST. Presence alone is satisfied by a component that flags every row;
      // absence alone is satisfied by one that flags none. Only both together say the classifier
      // discriminates — and they run against the same board, in the same render.
      const errors = collectPageErrors(page)
      const mock = await mockApi(page, withGames())
      await gotoTable(page, path)

      for (const player of [HEAVILY_LIMITED, LIMITED]) {
        const row = await rowFor(page, player.name)
        const flag = row.getByRole("button", { name: FLAG })
        await expect(
          flag,
          `${player.name} is projected for ${player.g} games and carries no availability flag`,
        ).toBeVisible()
        // ⛔ NOT "a badge rendered". The badge IS the games figure, so a chip showing the wrong
        // number — or a hardcoded one — is the failure that looks correct. The served value has to
        // be what is on the screen.
        await expect(
          flag,
          `${player.name}'s flag does not show his served games figure`,
        ).toContainText(player.shown)
      }

      for (const player of [AT_THRESHOLD, FULL_SEASON]) {
        const row = await rowFor(page, player.name)
        await expect(
          row.getByRole("button", { name: FLAG }),
          `${player.name} is flagged — the threshold is exclusive, so a row AT a full slate (or at ` +
            `the boundary itself) must render the plain figure`,
        ).toHaveCount(0)
      }

      await expectNoNaN(page)
      expectApiFullyMocked(mock)
      expectNoPageErrors(errors)
    })

    test(`${surface}: an unflagged row still renders its games figure`, async ({ page }) => {
      // ⚠️ THE QUIET REGRESSION. `AvailabilityFlag` REPLACED the games cell on three surfaces; had
      // it returned nothing for an unflagged row, ~95% of every board would have lost the column
      // outright — and an empty cell always looks deliberate. The Python suite pins the fall-through
      // in source; this pins that the fall-through actually renders.
      const mock = await mockApi(page, withGames())
      await gotoTable(page, path)

      const headers = await page.locator("table thead th").allInnerTexts()
      const games = headers.findIndex((h) => h.includes("Proj. games"))
      expect(games, "the projected-games column is gone").toBeGreaterThanOrEqual(0)

      const row = await rowFor(page, FULL_SEASON.name)
      const cell = (await row.locator("td").nth(games).innerText()).trim()
      expect(cell, `an unflagged games cell rendered "${cell}"`).toMatch(/^\d+(\.\d+)?$/)

      expectApiFullyMocked(mock)
    })
  }

  test("the player page flags the same row the boards flag", async ({ page }) => {
    // The surface a drafter reaches HAVING ALREADY noticed the low number on a board. If the three
    // disagreed about which rows are flagged, the click-through would silently contradict the board
    // that prompted it — which is why all three share one classifier.
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, withGames())

    await page.goto(`/fantasy/player/${HEAVILY_LIMITED.id}`)
    await expect(page.getByRole("heading", { name: HEAVILY_LIMITED.name })).toBeVisible()
    await expect(
      page.getByRole("button", { name: FLAG }),
      "the player page does not flag a row the boards flag",
    ).toBeVisible()

    await page.goto(`/fantasy/player/${FULL_SEASON.id}`)
    await expect(page.getByRole("heading", { name: FULL_SEASON.name })).toBeVisible()
    await expect(
      page.getByRole("button", { name: FLAG }),
      "the player page flags a full-season row",
    ).toHaveCount(0)

    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })
})

test.describe("the availability flag — what it says", () => {
  test("the definition opens on TAP and refuses the injury reading out loud", async ({ page }) => {
    // ⭐ THE CLAUSE A SOURCE SCAN CANNOT MAKE — and it only makes it on the `mobile` project. On
    // desktop Chromium `click()` dispatches `pointerenter` first and `InfoTip` opens on hover for a
    // mouse, so the popover is open before the click lands and a Radix TOOLTIP (which no touch can
    // ever open) would pass identically. On Pixel 7 there is no hover and `pointerType` is "touch",
    // so only the tap can open it.
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, withGames())
    await gotoTable(page, "/fantasy/rankings")

    const row = await rowFor(page, HEAVILY_LIMITED.name)
    await row.getByRole("button", { name: FLAG }).click()

    // ⚠️ Scoped to the POPOVER, not to the page text. The boards carry the projected-games
    // definition in a column header a few hundred pixels away, so a bare text match would be
    // satisfied whether or not the tap did anything — and whether the tap did anything is the
    // entire subject of this test.
    const definition = page.getByRole("dialog")
    await expect(definition, "the availability definition did not open on tap").toBeVisible()

    const text = (await definition.innerText()).toLowerCase()

    // The per-player figure, interpolated from the served payload rather than typed.
    expect(text, "the summary does not carry the served games figure").toContain(
      `projected ${HEAVILY_LIMITED.shown} games`,
    )

    // ⛔⛔ THE SENTENCE THAT MAKES AN AMBER CHIP PUBLISHABLE. The colour reads as "injury risk" all
    // by itself, whatever the words avoid saying — so the words have to refuse it explicitly. This
    // is the clause that would go quietly missing in a copy trim.
    expect(text, "the definition no longer states it is not a diagnosis").toContain(
      "not a diagnosis",
    )
    expect(text, "the definition dropped the hedge that availability is not the whole story")
      .toContain("not the only reason")

    // …and no medical forecast survived into the rendered text. Held HERE as well as in Python
    // because this popover composes three constants plus component chrome, and the composition is
    // the thing a reader meets.
    for (const forecast of ["will miss", "injury risk", "is hurt", "sidelined", "out for"]) {
      expect(text, `the flag's definition forecasts an injury (${forecast})`).not.toContain(
        forecast,
      )
    }

    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("nothing the flag renders makes a forbidden claim", async ({ page }) => {
    // The flag ships on the free, public, unauthenticated boards — the most-read surfaces in the
    // product — and it is static component copy, which is the category no export-side denylist has
    // ever seen. Run over the OPENED popover as well as the page, since the popover's text is not
    // in the DOM until it is opened.
    const mock = await mockApi(page, withGames())
    await gotoTable(page, "/fantasy/rankings")
    const row = await rowFor(page, LIMITED.name)
    await row.getByRole("button", { name: FLAG }).click()
    await expect(page.getByRole("dialog")).toBeVisible()

    const rendered = (await page.locator("body").innerText()).replace(/\s+/g, " ")
    expect(forbiddenPhrasesIn(rendered), "the flagged board makes a forbidden claim").toEqual([])

    expectApiFullyMocked(mock)
  })
})

test.describe("the availability flag — freshness and entitlement", () => {
  test("the injury-data vintage renders when the payload carries it", async ({ page }) => {
    // NF-FRESH2 stamped `sleeper_status_as_of` into the payload and NOTHING ever read it back — a
    // stamp nothing reads is not a freshness guarantee (NF-INJ1). ⚠️ Both shipped fixtures carry
    // `freshness: null`, so without planting one this assertion would be vacuous in the direction
    // that matters: it would pass on a build that never renders the line.
    const mock = await mockApi(page, {
      ...withGames(),
      transform: (pathname, body) => {
        const planted = withGames().transform!(pathname, body)
        if (pathname === "/fantasy/nfl/manifest") {
          return {
            ...planted,
            freshness: { input_vintage: { sleeper_status_as_of: "2026-08-19T11:00:00+00:00" } },
          }
        }
        return planted
      },
    })
    await gotoTable(page, "/fantasy/rankings")

    const row = await rowFor(page, HEAVILY_LIMITED.name)
    await row.getByRole("button", { name: FLAG }).click()
    const definition = page.getByRole("dialog")
    await expect(definition).toBeVisible()
    await expect(
      definition,
      "the flag does not name the vintage of the feed it rests on",
    ).toContainText(/injury and roster status as of\s*8\/19/i)

    expectApiFullyMocked(mock)
  })

  test("a payload with no vintage says nothing rather than inventing 'unknown'", async ({
    page,
  }) => {
    // ⚠️ THE OTHER HALF OF NF-FRESH2'S RULE, and the direction a naive implementation gets wrong.
    // ABSENT means "this payload predates the stamp" — which is every payload during an NF-C0
    // deploy-skew window — and describing it as unknown would put a scary word under every flag on
    // a routine deploy day. (NULL means "we looked and could not tell" and DOES render as unknown;
    // that branch is held in Python, where the two states are directly readable.)
    const mock = await mockApi(page, withGames())
    await gotoTable(page, "/fantasy/rankings")

    const row = await rowFor(page, HEAVILY_LIMITED.name)
    await row.getByRole("button", { name: FLAG }).click()
    const definition = page.getByRole("dialog")
    await expect(definition).toBeVisible()
    await expect(definition).not.toContainText(/injury and roster status as of/i)

    expectApiFullyMocked(mock)
  })

  test("a locked row is never flagged", async ({ page }) => {
    // ⛔ NF-LEAK1. E9.56's redaction strips `g` from the row and renders a subscribe chip in its
    // place; a flag beside that chip would DISCLOSE the withheld value's neighbourhood on exactly
    // the rows the server withheld it from, while claiming to describe a number the reader cannot
    // see. The transform still plants low games values, so this fails loudly if the classifier
    // ever reads a value the redaction was supposed to have removed.
    const mock = await mockApi(page, withGames({ entitlement: "locked" }))
    await gotoTable(page, "/fantasy/rankings")

    await expect(
      page.getByRole("button", { name: FLAG }),
      "a locked board rendered an availability flag — the withheld games value has leaked",
    ).toHaveCount(0)

    expectApiFullyMocked(mock)
  })
})
