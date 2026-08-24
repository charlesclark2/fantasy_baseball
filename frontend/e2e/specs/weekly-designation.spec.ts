import { expect, test, type Page } from "@playwright/test"
import { collectPageErrors, mockApi, type MockOptions } from "../support/api-mock"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"

/**
 * NF-C9 — THE WEEKLY GAME-STATUS DESIGNATION, at the render level.
 *
 * THE GAP. The availability discount fires on a formal ROSTER TRANSACTION (injured reserve / PUP /
 * non-football-injury / suspension) and on nothing else, so a player carrying a weekly game-status
 * designation — Questionable, Doubtful, Out — is projected with a discount of exactly ZERO. That is
 * leakage-safe and working as designed, and it is not what a reader assumes when they meet an "Out"
 * player at a normal-looking projected-games figure. NF-C9 DISCLOSES the designation and models
 * nothing: the chip renders beside `g`, and the sentence behind it says our number does not price
 * it in.
 *
 * ⭐ WHY THIS NEEDS A BROWSER, given `test_nf_c9_designation_disclosure.py` already exists. That
 * suite proves the COPY is honest and that all three surfaces BIND the component. Neither is a
 * property a READER has, and both are satisfiable by a page that renders nothing:
 *
 *   1. THE CHIP MUST APPEAR ON THE DESIGNATED ROWS AND ONLY THOSE. A component that renders on
 *      every row is decoration; one that renders on none is indistinguishable from the gap it
 *      closes. Both are green in `tsc` and in every source scan.
 *   2. THE DISCLAIMER MUST OPEN ON TAP. `InfoTip` is Popover-based precisely because a Radix
 *      Tooltip closes on pointerdown and can never be opened by a touch. A source scan sees
 *      `<InfoTip>` either way; only a real tap on a hover-less viewport tells them apart — see the
 *      `mobile` project in `playwright.config.ts`, which this spec is registered in. A bare chip
 *      reading "OUT" with an unreachable disclaimer is strictly worse than no chip.
 *   3. ⭐⭐ THE THREE STATES MUST RENDER AS THREE THINGS. Absent → nothing, null → "unknown",
 *      a value → the designation. Those are three different facts about what we know, and the two
 *      ways to collapse them are opposite failures: "unknown" on ~93% of every board, or an
 *      unreadable status quietly reading as a clean bill of health.
 *
 * ⛔⛔ THE FIXTURE IS PLANTED, AND IT HAS TO BE. Neither shipped fixture carries `gameStatus` at
 * all — so asserted against them as-is, "no chip on an undesignated row" would pass on a build
 * where the feature does not exist, and "a chip on a designated row" would have no row to run on.
 * That is the NF-C4/NF-C6P3 lesson: a fixture that cannot distinguish the correct implementation
 * from the broken one tests neither. `withDesignations` plants all three states.
 */

/** ⭐ ONE ROW PER STATE, and the fourth is the control.
 *
 *  ⚠️ NONE OF THEM CARRIES A LOW `g`, and that is deliberate rather than incidental. The whole
 *  point of NF-C9 being its own component is that a designation is INDEPENDENT of the availability
 *  flag — Jordyn Tyson, the row that produced NF-C8's finding, sat at 13.6 projected games (ABOVE
 *  `LIMITED_AVAILABILITY_GAMES`), so he carries a designation and NO flag. A fixture whose
 *  designated rows were also flagged could not tell a correct implementation from one nested inside
 *  `AvailabilityFlag`, which would miss exactly that player. */
const OUT = { name: "Jonathan Taylor", id: "00-0036223", status: "Out", chip: "OUT" }
const QUESTIONABLE = {
  name: "Justin Jefferson",
  id: "00-0036322",
  status: "Questionable",
  chip: "Q",
}
/** The feed said something the build could not read. `NA` and `DNR` are REAL values on the live
 *  snapshot (measured 2026-08-22: 13 and 2 rows), so this is production behaviour, not a
 *  hypothetical — and its correct rendering is an explicit "unknown", never silence. */
const UNKNOWN = { name: "Derrick Henry", id: "00-0032764", status: null, chip: "unknown" }
/** Untouched: the key is ABSENT, which is the normal state for ~93% of players. Renders nothing. */
const ABSENT = { name: "Zay Jones", id: "00-0033891" }

const PLANTED: Record<string, string | null> = {
  [OUT.id]: OUT.status,
  [QUESTIONABLE.id]: QUESTIONABLE.status,
  [UNKNOWN.id]: UNKNOWN.status,
}

/** The chip's rendered trigger. Located by its ACCESSIBLE NAME rather than by a class or a colour:
 *  the accessible name is what a screen reader gets and what a colour-blind reader depends on, and
 *  it carries the designation SPELLED OUT, which the two-character chip does not. */
const CHIP = /weekly game-status designation/i

/**
 * Plant the three states on every payload that carries player rows.
 *
 * ⚠️ ALL THREE PATHS, not just the board. `projections-table` reads `projections-full` when it can
 * and falls back to `projections`; the player page joins the projections blob to the board. A
 * transform covering only one would leave a surface silently testing the un-planted fixture — i.e.
 * passing because nothing renders there either.
 *
 * ⚠️ `id in PLANTED` RATHER THAN A TRUTHINESS TEST, because `UNKNOWN.status` IS null: the whole
 * subject of this spec is that an explicit null and an absent key are different, so a transform
 * that dropped the null while planting the strings would quietly delete the state under test.
 */
function withDesignations(extra?: Partial<MockOptions>): MockOptions {
  return {
    ...extra,
    transform: (pathname, body) => {
      const patch = (p: any) =>
        p?.id in PLANTED ? { ...p, gameStatus: PLANTED[p.id] } : p
      if (pathname === "/fantasy/nfl/board" && Array.isArray(body)) return body.map(patch)
      if (pathname.startsWith("/fantasy/nfl/projections") && Array.isArray(body?.players)) {
        return { ...body, players: body.players.map(patch) }
      }
      return extra?.transform ? extra.transform(pathname, body) : body
    },
  }
}

/** The board/projections tables paginate and sort, so a named row is reached through the search box
 *  rather than by index (the `freemium-board.spec.ts` pattern). */
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

test.describe("the weekly designation — which rows carry it, and what it shows", () => {
  for (const [surface, path] of [
    ["Rankings", "/fantasy/rankings"],
    ["Projections", "/fantasy/projections"],
  ] as const) {
    test(`${surface}: each of the three states renders as itself`, async ({ page }) => {
      // ⭐ THE FOUR ROWS ARE THE TEST, in one render against one board. Presence alone is satisfied
      // by a component that renders on every row; absence alone by one that renders on none; and
      // only the null row separates "we could not read the feed's value" from "there was nothing
      // to read".
      const errors = collectPageErrors(page)
      const mock = await mockApi(page, withDesignations())
      await gotoTable(page, path)

      for (const player of [OUT, QUESTIONABLE, UNKNOWN]) {
        const row = await rowFor(page, player.name)
        const chip = row.getByRole("button", { name: CHIP })
        await expect(
          chip,
          `${player.name} is served gameStatus=${JSON.stringify(player.status)} and renders no ` +
            `designation — the gap NF-C8 found stays invisible on this row`,
        ).toBeVisible()
        // ⛔ NOT "a chip rendered". A chip showing the wrong designation — or a hardcoded one — is
        // the failure that looks correct, and on this field a wrong value is a false claim about a
        // named person's game status.
        await expect(
          chip,
          `${player.name}'s chip does not show his served designation`,
        ).toHaveText(player.chip)
      }

      const absent = await rowFor(page, ABSENT.name)
      await expect(
        absent.getByRole("button", { name: CHIP }),
        `${ABSENT.name} carries no designation in the payload and a chip rendered anyway — an ` +
          `absent key must render NOTHING, never an invented status and never "unknown"`,
      ).toHaveCount(0)

      await expectNoNaN(page)
      expectApiFullyMocked(mock)
      expectNoPageErrors(errors)
    })
  }

  test("the player page discloses the same designation the boards do", async ({ page }) => {
    // ⭐⭐ THE SURFACE THE MOTIVATING CASE ACTUALLY LANDS ON, and the one a nested implementation
    // would silently skip: none of these rows is flagged for limited availability, so a designation
    // rendered from inside the player page's availability-tier branch appears on none of them.
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, withDesignations())

    await page.goto(`/fantasy/player/${OUT.id}`)
    await expect(page.getByRole("heading", { name: OUT.name })).toBeVisible()
    const chip = page.getByRole("button", { name: CHIP })
    await expect(
      chip,
      "the player page does not disclose a designation the boards disclose",
    ).toBeVisible()
    await expect(chip).toHaveText(OUT.chip)

    await page.goto(`/fantasy/player/${ABSENT.id}`)
    await expect(page.getByRole("heading", { name: ABSENT.name })).toBeVisible()
    await expect(
      page.getByRole("button", { name: CHIP }),
      "the player page invents a designation for a player the feed says nothing about",
    ).toHaveCount(0)

    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })
})

test.describe("the weekly designation — what it says", () => {
  test("the disclaimer opens on TAP and refuses the adjustment reading out loud", async ({
    page,
  }) => {
    // ⭐ THE CLAUSE A SOURCE SCAN CANNOT MAKE — and it only makes it on the `mobile` project. On
    // desktop Chromium `click()` dispatches `pointerenter` first and `InfoTip` opens on hover for a
    // mouse, so the popover is open before the click lands and a Radix TOOLTIP (which no touch can
    // ever open) would pass identically. On Pixel 7 there is no hover and `pointerType` is "touch",
    // so only the tap can open it.
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, withDesignations())
    await gotoTable(page, "/fantasy/rankings")

    const row = await rowFor(page, OUT.name)
    await row.getByRole("button", { name: CHIP }).click()

    // ⚠️ Scoped to the POPOVER, not to the page text — the boards carry a projected-games definition
    // in a column header a few hundred pixels away, and whether the tap did anything is the entire
    // subject of this test.
    const definition = page.getByRole("dialog")
    await expect(definition, "the designation's disclaimer did not open on tap").toBeVisible()

    const text = (await definition.innerText()).toLowerCase()

    // The served designation, interpolated rather than typed.
    expect(text, "the summary does not carry the served designation").toContain(
      `listed ${OUT.status.toLowerCase()}`,
    )

    // ⛔⛔ THE SENTENCE THE WHOLE STORY IS FOR. A chip beside a games figure reads as an adjustment
    // by POSITION alone, whatever the words omit — so the words have to refuse it. This is the
    // clause that would go quietly missing in a copy trim, and its absence would be invisible:
    // the chip renders perfectly well without it.
    expect(
      text,
      "the disclaimer no longer says our projected-games figure is unaffected — the chip then " +
        "reads as a discount we applied, which is exactly the false impression NF-C8 found",
    ).toContain("does not take this into account")

    expect(text, "the disclaimer no longer states it is not a diagnosis").toContain(
      "not a diagnosis",
    )

    // …and no medical forecast, and no invented duration, survived into the rendered text. Held
    // HERE as well as in Python because this popover composes four constants plus component
    // chrome, and the composition is the thing a reader meets.
    for (const forecast of ["will miss", "injury risk", "is hurt", "sidelined", "out for"]) {
      expect(text, `the disclaimer forecasts an injury (${forecast})`).not.toContain(forecast)
    }
    for (const duration of ["weeks", "rest of the season", "multi-week"]) {
      expect(
        text,
        `the disclaimer implies a duration (${duration}) — a weekly designation carries none`,
      ).not.toContain(duration)
    }

    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("NF-C10: the disclosure stamps the FEED's vintage, never the player's status", async ({
    page,
  }) => {
    // ⭐⭐ THE CONTRADICTION NF-C10 REMOVES, PINNED WHERE IT WAS LIVE. This popover says, in the
    // paragraph above, that we hold this designation and our projected-games figure DOES NOT take
    // it into account — and then stamped a line reading "Injury and roster STATUS as of {date}"
    // directly beneath it. "Status as of" reads as "we know his standing and applied it": the two
    // sentences contradicted each other, inside one tooltip, on every surface they share.
    //
    // ⚠️ PINNED ON THE RENDERED OUTPUT OF **THIS** SURFACE (NF-INJ1-C). The same helper feeds the
    // availability flag, and `availability-flag.spec.ts` pins it there — but a guard on the sibling
    // surface is not a pin on this one, and this is the surface where the wording actually clashed.
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, {
      ...withDesignations(),
      transform: (pathname, body) => {
        const planted = withDesignations().transform!(pathname, body)
        const vintage = { input_vintage: { sleeper_status_as_of: "2026-08-19T11:00:00+00:00" } }
        if (pathname === "/fantasy/nfl/manifest") return { ...planted, freshness: vintage }
        return planted
      },
    })
    await gotoTable(page, "/fantasy/rankings")

    const row = await rowFor(page, OUT.name)
    await row.getByRole("button", { name: CHIP }).click()
    const definition = page.getByRole("dialog")
    await expect(definition).toBeVisible()

    // Non-vacuity first: the disclosure's own sentence must be present, so this cannot pass on a
    // popover that failed to open or rendered empty.
    await expect(definition).toContainText(/does not take this into account/i)
    await expect(
      definition,
      "the disclosure carries no feed vintage — the stamp is planted, so it should render",
    ).toContainText(/injury\/roster feed as of\s*8\/19/i)
    await expect(
      definition,
      'the RETIRED "Injury and roster status as of" wording is still rendered here — beneath a ' +
        "sentence saying we do NOT act on this designation, which is the contradiction NF-C10 " +
        "exists to remove",
    ).not.toContainText(/injury and roster status as of/i)

    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("an unreadable value says 'unknown' AND still carries the disclaimer", async ({ page }) => {
    // ⭐ THE BRANCH A READER HAS LEAST TO GO ON. "unknown" with no statement about whether we priced
    // it reads MORE like a model input than a designation does — so the disclaimer has to render
    // here too, and a component that hung it off the recognised branch would look complete.
    const mock = await mockApi(page, withDesignations())
    await gotoTable(page, "/fantasy/rankings")

    const row = await rowFor(page, UNKNOWN.name)
    await row.getByRole("button", { name: CHIP }).click()
    const definition = page.getByRole("dialog")
    await expect(definition).toBeVisible()

    const text = (await definition.innerText()).toLowerCase()
    expect(text, "the unknown branch does not say we could not read the value").toContain(
      "do not recognise",
    )
    expect(
      text,
      "an unreadable designation renders with no disclaimer — a reader cannot tell whether it " +
        "moved the projection",
    ).toContain("does not take this into account")

    // ⛔ And it must not print the raw token it declined to interpret: publishing a code we refuse
    // to define asks the reader to interpret it for us.
    expect(text, "the unknown branch prints a raw feed token").not.toMatch(/\b(na|dnr|cov)\b/)

    expectApiFullyMocked(mock)
  })

  test("nothing the designation renders makes a forbidden claim", async ({ page }) => {
    // These strings ship on the free, public, unauthenticated boards — the most-read surfaces in
    // the product — and they are static component copy, the category no export-side denylist has
    // ever seen. Run over the OPENED popover as well as the page, since the popover's text is not
    // in the DOM until it is opened.
    const mock = await mockApi(page, withDesignations())
    await gotoTable(page, "/fantasy/rankings")
    const row = await rowFor(page, QUESTIONABLE.name)
    await row.getByRole("button", { name: CHIP }).click()
    await expect(page.getByRole("dialog")).toBeVisible()

    const rendered = (await page.locator("body").innerText()).replace(/\s+/g, " ")
    expect(forbiddenPhrasesIn(rendered), "the designated board makes a forbidden claim").toEqual([])

    expectApiFullyMocked(mock)
  })

  test("the chip's accessible name spells the designation out", async ({ page }) => {
    // ⚠️ THE CHIP IS TWO CHARACTERS AND A COLOUR. "Q" is meaningless to a screen reader and a
    // slate border is meaningless to a colour-blind reader, so the accessible name is the only
    // channel that carries the actual fact for both (WCAG 1.4.1) — and it is what every locator in
    // this spec depends on.
    const mock = await mockApi(page, withDesignations())
    await gotoTable(page, "/fantasy/rankings")

    for (const player of [OUT, QUESTIONABLE]) {
      const row = await rowFor(page, player.name)
      await expect(
        row.getByRole("button", { name: new RegExp(`designation: ${player.status}`, "i") }),
        `${player.name}'s chip does not spell "${player.status}" out in its accessible name — a ` +
          `screen reader gets "${player.chip}" and nothing else`,
      ).toBeVisible()
    }

    expectApiFullyMocked(mock)
  })
})
