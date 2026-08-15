import { expect, test, type Page } from "@playwright/test"
import {
  E2E_LINKED_LEAGUES,
  E2E_UNMATCHED_ROSTER_NAME,
  collectPageErrors,
  mockApi,
} from "../support/api-mock"
import { signIn } from "../support/session"
import { forbiddenPhrasesIn } from "../support/claim-denylist"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"

/**
 * NF-C6P2 — THE POST-DRAFT ROSTER REPORT, across entitlement states.
 *
 * ══ WHAT ONLY A BROWSER CAN SEE HERE ═══════════════════════════════════════════════════════════
 *
 * The report is an AGGREGATOR: `lib/roster-report.ts` sums and ranks values the server already
 * computed. Its failure modes are therefore not crashes — they are numbers that render perfectly and
 * are wrong, and a page that renders NOTHING and looks like a content problem. Four of those are
 * pinned below, each because it has a shipped precedent in this repo:
 *
 *   1. THE HEADLINE MUST BE THE SUM OF WHAT IS ON SCREEN. A team total that does not equal its own
 *      starting lineup is the "plausible-looking wrong number" class (E9.46's rank). It is asserted
 *      as ARITHMETIC — the rendered season column is added up and compared — so a lineup built from
 *      one set of players and a total computed over another fails, and a mere "a number rendered"
 *      implementation cannot pass.
 *   2. AN UNRESOLVED ROSTER ROW MUST BE NAMED. Scoring it as zero understates the team; dropping it
 *      silently overstates the coverage. Both render fine. (NF1.7 (a): a check that could not run is
 *      not a pass.)
 *   3. THE FOUR EMPTY STATES MUST BE DISTINCT. NF-C6 shipped the bug where "you never picked a team"
 *      and "your league has not drafted" shared a message and told a user to redo something they had
 *      already done — and "we could not read the board" must not present as either.
 *   4. THE UPGRADE PROMPT MUST BE ENTITLEMENT-GATED AND HONESTLY WORDED. Selling a subscriber what
 *      they already pay for reads as a billing bug; an outcome promise on the conversion surface is
 *      the claim the denylist exists to stop.
 *
 * ⛔ WHAT THIS FILE DOES NOT PROVE. Entitlement, again: the API is mocked and `signIn` seeds a
 * session into localStorage with no server involvement, so a browser assertion about authorization
 * would be the most convincing vacuous guard available. Who may read `/fantasy/nfl/league-board` is
 * asserted against the real ASGI app in `betting_ml/tests/test_g100_c1_free_league.py`. What is
 * asserted here is what a signed-in caller SEES.
 */

const FREE = { groups: [] as string[] }
const SUBSCRIBER = { groups: ["subscriber"] }

async function openReport(
  page: Page,
  opts: {
    groups?: string[]
    leagues?: "none" | "one" | "drafted" | "linked" | "predraft"
    fail?: string[]
    transform?: (path: string, body: any) => any
  } = {},
) {
  const errors = collectPageErrors(page)
  await signIn(page, { groups: opts.groups ?? [] })
  const mock = await mockApi(page, {
    entitlement: "entitled",
    leagues: opts.leagues ?? "drafted",
    fail: opts.fail,
    transform: opts.transform,
  })
  await page.goto("/fantasy/roster-report")
  await expect(page.getByRole("heading", { name: "Your roster, read against your league" })).toBeVisible()
  return { errors, mock }
}

/** Every number in one column of a table, as floats. Blank/em-dash cells are dropped. */
async function columnValues(page: Page, testId: string): Promise<number[]> {
  const raw = await page.locator(`[data-testid="${testId}"]`).allInnerTexts()
  return raw
    .map((t) => Number(t.trim().replace(/,/g, "")))
    .filter((v) => Number.isFinite(v))
}

test.describe("the report is built from the served board", () => {
  test("the headline total is the sum of the starting lineup it renders", async ({ page }) => {
    const { errors, mock } = await openReport(page, { groups: FREE.groups })

    await expect(page.getByTestId("roster-report")).toBeVisible()

    // ⭐ THE ARITHMETIC. Not "a total rendered" — the total must BE the sum of the season column of
    // the lineup table directly above it. A report that summed the whole roster (bench included),
    // or that filled the lineup from one list and totalled another, renders just as cleanly and
    // fails this. Tolerance is 0.55: every cell is rendered to one decimal, so ten starters carry
    // up to 0.05 each of rounding.
    const total = Number((await page.getByTestId("team-total").innerText()).replace(/,/g, ""))
    const lineup = await columnValues(page, "lineup-season-pts")
    expect(lineup.length, "the lineup table rendered no season points").toBeGreaterThan(0)
    const summed = lineup.reduce((a, b) => a + b, 0)
    expect(
      Math.abs(total - summed),
      `headline ${total} is not the sum of the ${lineup.length} rendered starters (${summed})`,
    ).toBeLessThan(0.55)

    await expectNoNaN(page)
    await expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("the 80% range brackets the total, and the correlated bound is at least as wide", async ({
    page,
  }) => {
    await openReport(page, { groups: FREE.groups })

    const total = Number((await page.getByTestId("team-total").innerText()).replace(/,/g, ""))
    const rangeText = await page.getByTestId("team-range").innerText()
    const [lo, hi] = rangeText.match(/[\d.,]+/g)!.map((s) => Number(s.replace(/,/g, "")))

    // A displayed interval must contain its own point estimate (NF1.7). This is cheap and it is the
    // assertion that catches a side being combined with the wrong sign.
    expect(lo).toBeLessThanOrEqual(total)
    expect(hi).toBeGreaterThanOrEqual(total)

    // ⭐ THE HONESTY CLAUSE. The rendered band assumes player seasons are INDEPENDENT, which
    // under-disperses a correlated sum (NF-W7b measured exactly that). The comonotone bound is
    // printed beside it so the assumption is bounded rather than merely disclosed — and it must
    // actually be the wider one, or the two have been swapped and the page is claiming the
    // pessimistic reading is the narrow one.
    const correlated = await page.getByTestId("team-range-correlated").innerText()
    const [clo, chi] = correlated.match(/[\d.,]+/g)!.map((s) => Number(s.replace(/,/g, "")))
    expect(clo).toBeLessThanOrEqual(lo)
    expect(chi).toBeGreaterThanOrEqual(hi)
  })

  test("a roster row we could not resolve is named, not silently dropped", async ({ page }) => {
    await openReport(page, { groups: FREE.groups })

    // The fixture roster carries exactly one unresolvable name (see `draftedRoster`). It must appear
    // in the coverage note — counting it as zero would understate the team and dropping it without
    // saying so would overstate what the report saw.
    const note = page.getByTestId("report-unmatched")
    await expect(note).toBeVisible()
    await expect(note).toContainText(E2E_UNMATCHED_ROSTER_NAME)
  })

  test("every section the epic names is present and non-empty", async ({ page }) => {
    await openReport(page, { groups: FREE.groups })

    // ⚠️ Presence is the WEAKEST of the assertions in this file and is deliberately not the only
    // one — the arithmetic tests above are what prove the numbers. This exists so a section that
    // silently stops rendering (a thrown-away branch, a renamed field) is a red build rather than a
    // quietly shorter page.
    for (const id of [
      "team-projection",
      "position-strengths",
      "starting-lineup",
      "bench-quality",
      "bye-conflicts",
      "fragility",
      "waiver-ideas",
      "trade-ideas",
    ]) {
      await expect(page.getByTestId(id), `the ${id} section is missing`).toBeVisible()
    }

    // The drafted fixture is built so the bench and trade sections have real content (see
    // `E2E_DRAFTED_LEAGUE`). Asserting the CONTENT rather than the container is what stops this
    // passing against a report whose every section rendered its "nothing to say" branch.
    await expect(page.getByTestId("bench-summary")).toBeVisible()
    expect(await page.getByTestId("position-row-RB").count()).toBe(1)
    expect(await page.getByTestId("lineup-row").count()).toBeGreaterThan(5)
  })

  test("the bye-week table costs a week the roster actually has off", async ({ page }) => {
    await openReport(page, { groups: FREE.groups })

    const rows = page.locator('[data-testid^="bye-week-"]')
    const count = await rows.count()
    expect(count, "no bye weeks rendered — the fixture roster carries real bye numbers").toBeGreaterThan(0)

    // A bye cost is a LOSS, so it can never be negative; and at least one week must cost something,
    // or the re-fill is not actually removing anybody (a lineup re-filled from the same pool
    // returns the same total and the whole section is decorative).
    const costs = await columnValues(page, `bye-cost-${(await firstByeWeek(page))}`)
    for (const c of costs) expect(c).toBeGreaterThanOrEqual(0)
    const all = await page.locator('[data-testid^="bye-cost-"]').allInnerTexts()
    const numeric = all.map((t) => Number(t.trim())).filter((v) => Number.isFinite(v))
    expect(numeric.some((v) => v > 0), `every bye week costs 0: ${all.join(", ")}`).toBe(true)
  })
})

async function firstByeWeek(page: Page): Promise<string> {
  const id = await page.locator('[data-testid^="bye-week-"]').first().getAttribute("data-testid")
  return (id ?? "bye-week-0").replace("bye-week-", "")
}

test.describe("the four empty states are four different messages", () => {
  test("no saved league at all", async ({ page }) => {
    const { mock } = await openReport(page, { groups: FREE.groups, leagues: "none" })
    await expect(page.getByTestId("report-empty-no-league")).toBeVisible()
    await expect(page.getByTestId("roster-report")).toHaveCount(0)
    await expectApiFullyMocked(mock)
  })

  test("a saved league with no team linked is NOT the same message", async ({ page }) => {
    // The captured league has `source_team_key: null` — a real state, and distinct both from "you
    // have no league" and from "your league has not drafted yet".
    await openReport(page, { groups: FREE.groups, leagues: "one" })
    await expect(page.getByTestId("report-empty-no-team-linked")).toBeVisible()
    await expect(page.getByTestId("report-empty-no-league")).toHaveCount(0)
    await expect(page.getByTestId("report-empty-not-drafted")).toHaveCount(0)
  })

  test("a LINKED team that has not drafted gets its own message", async ({ page }) => {
    // ⭐⭐ THE NF-C6 BUG, PINNED — AND THE CASE THE RED PROOF HAD TO FORCE INTO EXISTENCE.
    //
    // The first cut of this file asserted the ABSENCE of `report-empty-not-drafted` on the two modes
    // above and stopped there, which reads like coverage and is not: no fixture mode could PRODUCE
    // that state (`one` is the captured league, whose `source_team_key` is null), so the reason
    // branch was unreachable and collapsing the two reasons in `roster-report.ts` left the whole
    // suite green. That is the vacuous-guard class exactly, and it was found by breaking the source
    // rather than by reading the spec — which is what `leagues: "predraft"` now exists for.
    //
    // The distinction is not cosmetic. Telling someone whose league simply has not drafted to go and
    // "pick your team" sends them to redo something they already did, and nothing about re-importing
    // changes anything until the draft actually happens.
    await openReport(page, { groups: FREE.groups, leagues: "predraft" })
    await expect(page.getByTestId("report-empty-not-drafted")).toBeVisible()
    await expect(page.getByTestId("report-empty-no-team-linked")).toHaveCount(0)
    await expect(page.getByTestId("report-empty-no-league")).toHaveCount(0)
  })

  test("no bye weeks on the board says so, rather than inventing any", async ({ page }) => {
    // ⭐ THE NF-INFRA1 DEPENDENCY, MADE OBSERVABLE. Bye weeks come from the published projections
    // artifact, which derives them from the lake's `schedules` — and `bye_week_map` leaves them NULL
    // until the season lands, which is gated on NFL ingest schedules that ship STOPPED. (Measured on
    // the current served artifact they ARE populated, 858 of 858, so this is not blocking today —
    // but "it happens to be there right now" is not a design.)
    //
    // The requirement is that absent data produces an honest empty state and NEVER a fabricated
    // report. The failure mode worth pinning is not a crash: it is a bye table that renders week
    // "0", or an ⁠—-filled row, or silently drops the section so a reader concludes their roster has
    // no bye conflicts. So: strip every bye, and demand the rest of the report still stands while
    // the bye section says what it does not know.
    await openReport(page, {
      groups: FREE.groups,
      // ⚠️ BOTH ARRAYS. The first cut stripped `board.players` only and the test failed with a full
      // bye table — because the report reads each rostered player's bye off the JOINED row
      // (`roster[].board`), which the harness builds by reference and a spread over the other array
      // does not touch. A partial mutation is a red proof that proves nothing about the clause it
      // names; the failure was the harness working, not the app.
      transform: (path, body: any) => {
        if (path !== "/fantasy/nfl/league-board") return body
        const strip = (p: any) => (p == null ? p : { ...p, bye: null })
        return {
          ...body,
          board: { ...body.board, players: body.board.players.map(strip) },
          roster: body.roster.map((r: any) => ({ ...r, board: strip(r.board) })),
        }
      },
    })

    await expect(page.getByTestId("roster-report")).toBeVisible()
    await expect(page.getByTestId("team-total")).toBeVisible()
    await expect(page.getByTestId("bye-conflicts")).toContainText("No bye weeks are known")
    expect(await page.locator('[data-testid^="bye-week-"]').count()).toBe(0)
    await expectNoNaN(page)
  })

  test("a board we could not read reports a fault, not an empty roster", async ({ page }) => {
    // ⭐ `fail` makes the READ ITSELF fail, which `transform` structurally cannot express. "The
    // model published nothing" and "this page could not reach the model" are different facts and
    // the surface has to say which — a page that showed "no roster yet" here would send a user to
    // re-import a league that is perfectly fine.
    await openReport(page, {
      groups: FREE.groups,
      leagues: "drafted",
      fail: ["/fantasy/nfl/league-board"],
    })
    await expect(page.getByTestId("report-empty-no-board")).toBeVisible()
    await expect(page.getByTestId("roster-report")).toHaveCount(0)
    await expect(page.getByTestId("report-empty-not-drafted")).toHaveCount(0)
  })
})

test.describe("the season upgrade prompt", () => {
  test("a free account is offered it", async ({ page }) => {
    await openReport(page, { groups: FREE.groups })
    const prompt = page.getByTestId("season-upgrade-prompt")
    await expect(prompt).toBeVisible()
    await expect(prompt.getByRole("link", { name: "See membership options" })).toHaveAttribute(
      "href",
      "/subscribe",
    )
  })

  test("a subscriber is NOT sold what they already pay for", async ({ page }) => {
    // ⚠️ THE NEGATIVE HALF, and it is the one that matters. A prompt that renders for everybody
    // passes the positive test above and reads to a paying member as a billing bug.
    await openReport(page, { groups: SUBSCRIBER.groups })
    await expect(page.getByTestId("roster-report")).toBeVisible()
    await expect(page.getByTestId("season-upgrade-prompt")).toHaveCount(0)
  })

  test("nothing on the page promises an outcome", async ({ page }) => {
    // The whole rendered surface, not just the prompt: the denylist mirror exists because a
    // component's own static strings never pass through the export-side screening, and the
    // conversion surface is exactly where "win your league" would get typed.
    await openReport(page, { groups: FREE.groups })
    const text = await page.evaluate(() => document.body.innerText)
    expect(forbiddenPhrasesIn(text), "an overclaim reached the roster report").toEqual([])
  })
})

test.describe("the report follows the league that is selected", () => {
  test("switching leagues re-reads the board for THAT league", async ({ page }) => {
    // ⚠️ WHY THIS EXISTS. Until NF-C6P2 the harness answered `/fantasy/nfl/league-board` with the
    // first saved league whatever id was asked for, so a multi-league surface could select league B,
    // be served league A, and assert happily about the wrong roster. The mock now resolves the id —
    // which means this spec is also what keeps the harness honest.
    const { mock } = await openReport(page, { groups: SUBSCRIBER.groups, leagues: "linked" })

    // ⚠️ A Radix `Picker`, not a native <select> — `selectOption` silently does nothing on one, so
    // the trigger is clicked and then the option (`components/ui/picker.tsx` explains why the raw
    // element is forbidden repo-wide).
    await page.getByLabel("League", { exact: true }).click()
    await page.getByRole("option", { name: E2E_LINKED_LEAGUES.standard.name, exact: true }).click()

    await expect
      .poll(() =>
        mock.requested.filter((r) => r.includes(`league_id=${E2E_LINKED_LEAGUES.standard.id}`)).length,
      )
      .toBeGreaterThan(0)
    await expectApiFullyMocked(mock)
  })
})

test.describe("E9.46 — one rank, one meaning", () => {
  test("the home card's rank is the SERVER's, and the two populations are labelled apart", async ({
    page,
  }) => {
    // ══ WHAT THIS CAN AND CANNOT PROVE, STATED UP FRONT ═══════════════════════════════════════
    //
    // The rider is that "Our rank" means the FULL-BOARD within-position rank, so the home card and
    // /fantasy/rankings agree, while the ADP gap stays inside the matched set. THE POPULATION ITSELF
    // is asserted server-side, against the shipping selector, in
    // `test_e9_46_featured_player.py::test_our_rank_is_the_full_board_rank_at_a_deep_position` —
    // with a deliberately DEEP position, because the live selection (Kittle, TE21 under both
    // readings) is the one player on whom the defect is invisible.
    //
    // ⛔ IT CANNOT BE PROVEN BY COMPARING THE TWO RENDERED PAGES HERE, and pretending otherwise
    // would be the vacuous half of this suite. The two fixtures have different SOURCES: the featured
    // payload is generated from the REAL prod artifact (`build-featured-player.py`), while the board
    // is generated from the SYNTHETIC entitled projections (`build-entitled-fixture.mjs`, whose
    // values are seeded off the player id). They describe different numbers by construction, so an
    // equality assertion across them would fail on a correct build and could only ever be made to
    // pass by weakening it into nothing.
    //
    // What IS provable in a browser, and is what this asserts: the card renders the SERVER'S rank
    // rather than deriving one of its own, and it says out loud when the two populations differ.
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, {
      transform: (path, body: any) => {
        if (path !== "/fantasy/nfl/featured-player") return body
        // A rank the fixture cannot contain, plus a DIFFERENT matched rank — so the reconciliation
        // line is reachable and the tile cannot be echoing the same number twice.
        return { ...body, market: { ...body.market, ourRank: 137, ourRankAmongDrafted: 4 } }
      },
    })
    await page.goto("/")

    const card = page.locator("#fantasy-proof")
    await expect(card).toBeVisible()
    // ⭐ THE SERVER'S NUMBER, FOLLOWED. A card that computed its own rank — or that fell back to the
    // matched one — renders 4 here and fails. This is the E9.59 hardcoded-price shape: change the
    // server's value and demand the DOM move.
    await expect(card).toContainText("137")

    // …and the two populations are named apart rather than left for the reader to subtract.
    const note = page.getByTestId("rank-population-note")
    await expect(note).toBeVisible()
    await expect(note).toContainText("4")

    await expectNoNaN(page)
    await expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("the note stays away when the two ranks agree", async ({ page }) => {
    // ⚠️ THE ISOLATING HALF. Without it, a component that ALWAYS rendered the note would pass the
    // test above — and a permanent "these are different populations" line under a card where they
    // are not is its own small dishonesty.
    await mockApi(page, {
      transform: (path, body: any) =>
        path === "/fantasy/nfl/featured-player"
          ? { ...body, market: { ...body.market, ourRank: 21, ourRankAmongDrafted: 21 } }
          : body,
    })
    await page.goto("/")
    await expect(page.locator("#fantasy-proof")).toBeVisible()
    await expect(page.getByTestId("rank-population-note")).toHaveCount(0)
  })
})
