import { expect, test, type Page } from "@playwright/test"
import {
  E2E_LINEUP_GAP_LEAGUES,
  E2E_LINKED_LEAGUES,
  E2E_ROSTERED_DST,
  E2E_ROSTERED_IDP,
  E2E_ROSTERED_KICKER,
  E2E_UNMATCHED_ROSTER_NAME,
  collectPageErrors,
  linkedRosterStarters,
  linkedRosterSubject,
  mockApi,
} from "../support/api-mock"
import { signIn } from "../support/session"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"
import {
  PORTFOLIO_CAVEAT_FORMATS,
  PORTFOLIO_CAVEAT_LINEUP,
  PORTFOLIO_CAVEAT_SNAPSHOT,
  PORTFOLIO_BEST_LABEL,
  PORTFOLIO_NOTE,
} from "@/lib/fantasy-claim-copy"

/**
 * E9.64 — MY TEAMS (NF-C6): every imported league's roster, each scored under ITS OWN format.
 *
 * ══ THE CLAIM, AND WHY IT NEEDED A NEW FIXTURE MODE ═══════════════════════════════════════════
 *
 * "Scored under its own format" is the entire surface. The failure that breaks it is not a crash —
 * it is scoring every roster on ONE board and relabelling the cards, which renders perfectly, has
 * no NaN, throws nothing, and is wrong in a way the user cannot detect without doing the arithmetic
 * themselves. No Python test can see it either: the API hands back leagues and rosters, and what
 * the browser does with them is the whole question.
 *
 * The three pre-existing `leagues` modes could not express it. All of them serve the captured league
 * with `source_team_key: null` and a null roster — an honest state, and the only one they can make —
 * so every roster table on this surface was structurally unreachable and the cross-league claim had
 * nothing to compare. `leagues: "linked"` (see `api-mock.ts`) adds two linked leagues that differ in
 * EXACTLY ONE scoring rule, carrying the SAME players.
 *
 * ⭐ THAT MAKES THE ASSERTION ARITHMETIC RATHER THAN A VIBE. For a non-TE the two cards must differ
 * by exactly `0.5 × receptions`, computed below from the projections payload's own `rec`. A surface
 * that scored both rosters on one board renders identical numbers and fails; one that merely scored
 * them "differently" fails too, because the SIZE of the difference is pinned.
 *
 * ⚠️ WHO may open this is asserted in `fantasy-entitlement-gates.spec.ts`. This file signs in as a
 * subscriber and asks only whether the surface is CORRECT.
 */

/** The card for one league, located by its name. */
function leagueCard(page: Page, name: string) {
  return page.locator("section").filter({ hasText: name }).first()
}

/** The expected-points cell for one player inside one league's card. */
async function pointsFor(page: Page, leagueName: string, playerName: string): Promise<number> {
  const row = leagueCard(page, leagueName).locator("tbody tr").filter({ hasText: playerName }).first()
  await expect(row, `${playerName} is not on the ${leagueName} roster`).toBeVisible()
  const text = (await row.locator("td").nth(3).innerText()).trim()
  const value = Number(text.replace(/,/g, ""))
  expect(
    Number.isFinite(value),
    `${playerName}'s points rendered as "${text}" in ${leagueName} — not a number`,
  ).toBe(true)
  return value
}

async function openMyTeams(
  page: Page,
  // `drafted` is the single-league post-draft fixture — NF-C6b uses it for the "one team gets a
  // total but no ranking" case, which `linked` (two leagues) structurally cannot express.
  leagues: "linked" | "none" | "one" | "drafted" | "lineupGap" | "kdstGap" = "linked",
) {
  const errors = collectPageErrors(page)
  await signIn(page, { groups: ["subscriber"] })
  const mock = await mockApi(page, { entitlement: "entitled", leagues })
  await page.goto("/fantasy/my-teams")
  await expect(page.getByRole("heading", { name: "My Teams" })).toBeVisible()
  return { errors, mock }
}

test.describe("every league is scored under its own format", () => {
  test("the same player is worth different points in two leagues that score receptions differently", async ({
    page,
  }) => {
    const { errors, mock } = await openMyTeams(page)

    // Both cards render, and they are distinct leagues rather than one card twice.
    await expect(leagueCard(page, E2E_LINKED_LEAGUES.half.name)).toBeVisible()
    await expect(leagueCard(page, E2E_LINKED_LEAGUES.standard.name)).toBeVisible()

    // The subject is read out of the harness's own roster, which was itself read out of the served
    // projections — nothing here is a hardcoded name.
    const subject = linkedRosterSubject()
    const half = await pointsFor(page, E2E_LINKED_LEAGUES.half.name, subject.name)
    const standard = await pointsFor(page, E2E_LINKED_LEAGUES.standard.name, subject.name)

    // ⭐ THE ARITHMETIC. Half-PPR pays 0.5 per reception and the twin pays 0; everything else about
    // the two leagues is byte-identical, so the gap is fixed by the player's own projected catches.
    // A single shared board makes this 0 and fails; a wrong scoring field makes it the wrong size.
    //
    // Tolerance is 0.11: each figure is rendered to one decimal, so each carries up to 0.05 of
    // rounding and the difference up to 0.10. Anything looser would stop pinning the SIZE of the
    // effect and only pin its sign, which a wrong-but-different scoring rule would satisfy.
    const expected = 0.5 * subject.rec
    expect(
      Math.abs(half - standard - expected),
      `the same player scored ${half} in half-PPR and ${standard} in the standard league; with ` +
        `${subject.rec} projected receptions the gap should be ${expected.toFixed(1)}. A gap of 0 ` +
        `means both rosters were scored on ONE board and the cards merely relabelled.`,
    ).toBeLessThanOrEqual(0.11)

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("starters and bench are separated, and an unresolvable name is counted rather than hidden", async ({
    page,
  }) => {
    const { errors } = await openMyTeams(page)
    const card = leagueCard(page, E2E_LINKED_LEAGUES.half.name)

    // Both tables — `RosterTable` returns null on an empty list, so a roster that lost its bench
    // renders a perfectly tidy card with a third of the team missing.
    await expect(card.getByText(/^Starters · \d+$/)).toBeVisible()
    await expect(card.getByText(/^Bench · \d+$/)).toBeVisible()

    // ⭐ THE ROW WE CANNOT SCORE MUST STILL APPEAR. Dropping it silently is the tempting
    // implementation and it is data loss on the user's own roster: they see 14 of their 15 players
    // and no statement that anything is missing.
    await expect(
      card.getByText(E2E_UNMATCHED_ROSTER_NAME),
      "a rostered player we could not match to a projection was dropped from the roster entirely",
    ).toBeVisible()
    await expect(
      card.getByText(/\d+ of \d+ rostered players matched to a season projection/),
      "the unmatched player is shown but never accounted for",
    ).toBeVisible()

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("each card states the format it was scored under", async ({ page }) => {
    // The numbers only mean anything beside the settings that produced them — and it is the one
    // thing that makes the difference above legible to a user rather than looking like a bug.
    const { errors } = await openMyTeams(page)

    await expect(leagueCard(page, E2E_LINKED_LEAGUES.half.name)).toContainText(/10-team/)
    await expect(leagueCard(page, E2E_LINKED_LEAGUES.half.name)).toContainText(/half/i)
    await expect(leagueCard(page, E2E_LINKED_LEAGUES.standard.name)).toContainText(/standard/i)
    expectNoPageErrors(errors)
  })
})

/**
 * ══ NF-C6b — THE CROSS-LEAGUE PORTFOLIO ROLLUP ═══════════════════════════════════════════════════
 *
 * My Teams already listed every team. What it had no answer for was the aggregate question a
 * multi-league subscription is bought for — "which of my teams is projecting the most?" — so NF-C6b
 * adds a per-team total and a ranked summary across leagues.
 *
 * ⭐ THE TOTAL'S CONTRACT IS ARITHMETIC AND IS ASSERTED AS ARITHMETIC: it must equal the sum of the
 * rows in that card's OWN Starters table. That rules out the three ways this goes quietly wrong —
 * totalling the whole roster (bench included), totalling OUR optimizer's best lineup instead of the
 * platform's reported starters (a real temptation, since `fillLineup` is right there in the
 * aggregator this reuses), and dropping an unscored starter without saying so. Each renders a
 * plausible number that the reader cannot check against the table beneath it.
 *
 * ⭐ AND THE RANKING'S SIZE IS PINNED, not just its order. The two linked leagues differ in exactly
 * one rule — 0.5 a reception against 0 — over identical rosters, so the gap between their totals is
 * fixed by the STARTERS' own receptions. An implementation that ranked on one shared board, or that
 * ranked on something other than the total, satisfies "half is first" and fails this.
 */
test.describe("the portfolio rollup", () => {
  /** Every rendered points figure in one card's Starters table. */
  async function starterPoints(page: Page, leagueName: string): Promise<number[]> {
    const rows = leagueCard(page, leagueName).getByTestId("starters-table").locator("tbody tr")
    // Visibility first, then poll the row count to the number the fixture actually starts — a
    // one-shot read here would race the render and could sum a partially-mounted table.
    await expect(rows.first(), `${leagueName} rendered no starters at all`).toBeVisible()
    await expect
      .poll(() => rows.count(), {
        message: `${leagueName}'s Starters table never settled at ${linkedRosterStarters().length} rows`,
      })
      .toBe(linkedRosterStarters().length)

    const texts = await rows.locator("td:nth-child(4)").allInnerTexts()
    return texts.map((t) => {
      const value = Number(t.trim().replace(/,/g, ""))
      expect(
        Number.isFinite(value),
        `a starter's points rendered as "${t}" in ${leagueName} — the total cannot be checked ` +
          `against a table that is not showing numbers`,
      ).toBe(true)
      return value
    })
  }

  /** One of the two figures on a card, by its test id. */
  async function cardValue(page: Page, leagueName: string, testId: string): Promise<number> {
    const cell = leagueCard(page, leagueName).getByTestId(testId)
    await expect(cell, `${leagueName} rendered no ${testId}`).toBeVisible()
    const text = (await cell.innerText()).trim()
    const value = Number(text.replace(/,/g, ""))
    expect(Number.isFinite(value), `${leagueName}'s ${testId} rendered as "${text}"`).toBe(true)
    return value
  }

  const asSetTotal = (page: Page, league: string) => cardValue(page, league, "team-as-set-value")
  const bestTotal = (page: Page, league: string) => cardValue(page, league, "team-best-value")

  test("each team's as-set total is exactly the sum of the starters shown on its own card", async ({
    page,
  }) => {
    // ⭐ THE CHECKABLE HALF. As-set is the figure a reader can verify by adding up the table under
    // it, and keeping that true is why as-set exists alongside best-possible at all.
    const { errors, mock } = await openMyTeams(page)

    for (const league of [E2E_LINKED_LEAGUES.half, E2E_LINKED_LEAGUES.standard]) {
      const points = await starterPoints(page, league.name)
      const total = await asSetTotal(page, league.name)
      const sum = points.reduce((a, b) => a + b, 0)

      // Tolerance 0.06: the server rounds each player's points to one decimal and the total is
      // rendered to one decimal, so these should agree exactly — the allowance is for float noise,
      // not for a genuine difference. Anything larger would stop the check being arithmetic.
      expect(
        Math.abs(total - sum),
        `${league.name} shows a current-starters total of ${total} over starters worth ` +
          `${points.join(" + ")} = ${sum.toFixed(1)}. A total that includes the bench, or that ` +
          `fields our optimizer's lineup instead of the platform's starters, lands here.`,
      ).toBeLessThanOrEqual(0.06)
    }

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("best-possible fields the bench, and the gap is exactly what it adds", async ({ page }) => {
    // ⭐ THE OTHER HALF, AND THE ONE THE RANKING USES. On the linked roster the optimizer can field
    // every matched player — the three platform starters PLUS the benched TE — because the league
    // starts ten and the roster holds four scoreable players. So best-possible is arithmetically
    // as-set + that TE, and the gap IS the TE. An implementation that quietly reused the platform
    // lineup for both figures produces a gap of 0 and fails here.
    const { errors } = await openMyTeams(page)
    const league = E2E_LINKED_LEAGUES.half

    const benchRows = leagueCard(page, league.name).getByTestId("bench-table").locator("tbody tr")
    await expect(benchRows.first(), "no bench rows rendered").toBeVisible()

    // The bench holds the TE plus one deliberately unresolvable name; only the scoreable one can be
    // fielded, so the gap is that single figure.
    const benchTexts = await benchRows.locator("td:nth-child(4)").allInnerTexts()
    const benchScoreable = benchTexts
      .map((t) => Number(t.trim().replace(/,/g, "")))
      .filter((v) => Number.isFinite(v))
    expect(
      benchScoreable.length,
      "the bench carries no scoreable player, so this fixture cannot tell a best-possible lineup " +
        "that fields the bench from one that does not",
    ).toBe(1)

    const asSet = await asSetTotal(page, league.name)
    const best = await bestTotal(page, league.name)

    expect(
      Math.abs(best - asSet - benchScoreable[0]),
      `best-possible ${best} minus current-starters ${asSet} should equal the one fieldable bench ` +
        `player (${benchScoreable[0]}). A gap of 0 means both figures were built from the same ` +
        `lineup and the optimizer never ran.`,
    ).toBeLessThanOrEqual(0.06)

    // And the hero line must actually state that gap, not merely compute it.
    const gapLine = leagueCard(page, league.name).getByTestId("team-gap")
    await expect(gapLine, "the bench gap is computed but never surfaced").toBeVisible()
    await expect(gapLine).toContainText(/Leaving .* projected points on your bench/i)

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("the summary ranks the teams, and the gap is the one scoring rule they differ by", async ({
    page,
  }) => {
    const { errors } = await openMyTeams(page)

    const summary = page.getByTestId("portfolio-summary")
    await expect(summary, "no cross-league summary rendered for a two-league account").toBeVisible()

    const rows = summary.getByTestId("portfolio-row")
    await expect
      .poll(() => rows.count(), { message: "the summary never settled at two ranked teams" })
      .toBe(2)

    // ⭐ NON-VACUITY, FIRST. If the fixture's starters caught no passes the two totals would be
    // equal, the ordering below would be arbitrary, and this test would pass while proving nothing.
    const expectedGap = 0.5 * linkedRosterStarters().reduce((n, s) => n + s.rec, 0)
    expect(
      expectedGap,
      "the linked fixture's starters have no receptions between them, so the two leagues score " +
        "identically and this test cannot tell a correct ranking from an arbitrary one",
    ).toBeGreaterThan(0)

    // Half-PPR pays for those receptions and the twin does not, so half MUST rank first.
    await expect(rows.nth(0), "the higher-scoring league is not ranked first").toContainText(
      E2E_LINKED_LEAGUES.half.name,
    )
    await expect(rows.nth(1)).toContainText(E2E_LINKED_LEAGUES.standard.name)

    const half = await asSetTotal(page, E2E_LINKED_LEAGUES.half.name)
    const standard = await asSetTotal(page, E2E_LINKED_LEAGUES.standard.name)
    expect(
      Math.abs(half - standard - expectedGap),
      `the two teams totalled ${half} and ${standard}; with ${expectedGap.toFixed(1)} of ` +
        `reception scoring between them the gap should be ${expectedGap.toFixed(1)}. A gap of 0 ` +
        `means both were totalled on ONE board and the rows merely relabelled.`,
    ).toBeLessThanOrEqual(0.11)

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("the ranking is ordered by BEST-POSSIBLE, not by the lineup as set", async ({ page }) => {
    // ⭐⭐ THE GATE THE `linked` FIXTURE CANNOT EXPRESS, and the reason `lineupGap` exists.
    //
    // In `linked` the half-PPR team leads on BOTH readings, so a summary that sorted on as-set
    // would rank identically and this assertion would prove nothing. Here the two orderings are
    // deliberately REVERSED: both leagues carry the same scoring, and the only difference is that
    // "Benched Talent FC" holds a better roster with almost all of it benched.
    //
    //   as-set        → Lineup Set FC first  (it starts three good players; the other starts a TE)
    //   best-possible → Benched Talent FC first (its roster is strictly the better one)
    //
    // So sorting on the wrong figure inverts the table, which is exactly what the PM's decision
    // turned on: as-set would rank lineup-setting diligence rather than roster strength.
    const { errors } = await openMyTeams(page, "lineupGap")

    const rows = page.getByTestId("portfolio-summary").getByTestId("portfolio-row")
    await expect
      .poll(() => rows.count(), { message: "the summary never settled at two ranked teams" })
      .toBe(2)

    // NON-VACUITY: the two orderings must genuinely disagree in this fixture, or the assertion
    // below is satisfied by either implementation.
    const setBest = await bestTotal(page, E2E_LINEUP_GAP_LEAGUES.set.name)
    const setAsSet = await asSetTotal(page, E2E_LINEUP_GAP_LEAGUES.set.name)
    const benchedBest = await bestTotal(page, E2E_LINEUP_GAP_LEAGUES.benched.name)
    const benchedAsSet = await asSetTotal(page, E2E_LINEUP_GAP_LEAGUES.benched.name)
    expect(
      benchedBest > setBest && benchedAsSet < setAsSet,
      `this fixture no longer separates the two orderings (best-possible ${benchedBest} vs ` +
        `${setBest}; as-set ${benchedAsSet} vs ${setAsSet}), so it cannot tell a summary ranked ` +
        `on best-possible from one ranked on the lineup as set`,
    ).toBe(true)

    await expect(
      rows.nth(0),
      "the summary ranked the team with the better LINEUP first, not the better ROSTER — it is " +
        "sorting on current starters instead of best-possible",
    ).toContainText(E2E_LINEUP_GAP_LEAGUES.benched.name)
    await expect(rows.nth(1)).toContainText(E2E_LINEUP_GAP_LEAGUES.set.name)

    // The team with nothing on its bench must say so rather than printing a fabricated gap.
    await expect(
      leagueCard(page, E2E_LINEUP_GAP_LEAGUES.set.name).getByTestId("team-gap"),
    ).toContainText(/already are our best lineup/i)

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("the ranking says what it ranks, and its caveats render with the table", async ({ page }) => {
    // ⛔ A STANDINGS-SHAPED TABLE ANSWERS "WHERE WILL I FINISH?" WHETHER OR NOT IT WAS ASKED, and
    // across leagues it also invites "which roster is best" — which these numbers cannot support,
    // because a half-PPR total is bigger than a standard one for the very same players. Each caveat
    // is asserted separately: a caveat behind a click is a caveat that did not render.
    const { errors } = await openMyTeams(page)
    const summary = page.getByTestId("portfolio-summary")
    await expect(summary).toBeVisible()

    await expect(summary, "the summary never says what it is ranking").toContainText(PORTFOLIO_NOTE)
    await expect(
      summary,
      "the cross-league summary does not warn that the totals come from different scoring systems",
    ).toContainText(PORTFOLIO_CAVEAT_FORMATS)
    await expect(
      summary,
      "the summary does not say whose lineup it totalled",
    ).toContainText(PORTFOLIO_CAVEAT_LINEUP)
    await expect(summary, "the summary does not date the rosters").toContainText(
      PORTFOLIO_CAVEAT_SNAPSHOT,
    )

    // The ranked figure must never appear without the label that says what it measures.
    await expect(summary).toContainText(PORTFOLIO_BEST_LABEL)

    const hits = forbiddenPhrasesIn(await page.locator("body").innerText())
    expect(hits, `the portfolio copy makes a forbidden claim: ${hits.join(", ")}`).toEqual([])

    expectNoPageErrors(errors)
  })

  test("a single league gets its total but no ranking", async ({ page }) => {
    // A "ranking" of one team is not one, and rendering it would dress a single number up as a
    // comparison. The card's own total still has to be there — that is the half that is meaningful.
    const { errors } = await openMyTeams(page, "drafted")

    await expect(page.getByTestId("team-total").first()).toBeVisible()
    await expect(
      page.getByTestId("portfolio-summary"),
      "a one-league account was shown a cross-league ranking of itself",
    ).toHaveCount(0)

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("the rollup never reaches a free account", async ({ page }) => {
    // The gate is the page's, and it is server-backed (`require_personalized_league_access` caps
    // what /my-teams serves). This asserts the rollup specifically: a free account is sent to the
    // upsell and no portfolio table renders on the way past.
    await signIn(page, { groups: [] })
    await mockApi(page, { entitlement: "free", leagues: "one" })
    await page.goto("/fantasy/my-teams")

    await page.waitForURL((url) => !url.pathname.startsWith("/fantasy/my-teams"), {
      timeout: 10_000,
    })
    expect(new URL(page.url()).pathname).toBe("/subscribe")
    await expect(
      page.getByTestId("portfolio-summary"),
      "the portfolio rollup rendered for an account without a membership",
    ).toHaveCount(0)
  })
})

test.describe("the states a real account is actually in", () => {
  test("no saved leagues says so, and points at both ways to fix it", async ({ page }) => {
    // The state every new subscriber is in. An empty surface with no instruction reads as broken.
    const { errors } = await openMyTeams(page, "none")

    await expect(page.getByText("No saved leagues yet")).toBeVisible()
    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("a saved league with no team linked is told what to do, not shown an empty roster", async ({
    page,
  }) => {
    // ⭐ THE DISTINCTION NF-C6 SHIPPED A BUG ON: "no team linked" and "linked, but the platform
    // reported no players" are different facts with different fixes, and `roster.length` alone
    // cannot tell them apart. `leagues: "one"` is the captured league — saved, never linked — which
    // is exactly the first case.
    const { errors } = await openMyTeams(page, "one")

    await expect(
      page.getByText(/No team linked yet/),
      "a league with no linked team rendered as though the roster were simply empty",
    ).toBeVisible()
    await expect(
      page.locator('a[href="/fantasy/import"]'),
      "the fix for an unlinked league is not offered on the card that has the problem",
    ).not.toHaveCount(0)

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })
})


// ══ NF-K1 — WHY a row has no projection, not just THAT it has none ══════════════════════════════
//
// 🔴 THE REGRESSION THIS SUITE COULD NOT SEE. On 2026-08-16 the published board carried 795 players
// and ZERO K, ZERO D/ST, so every rostered kicker and defence rendered the single word "not
// matched" — wording that describes a NAME-RESOLUTION failure and duly sent two investigations at
// the NF-C6P3 D/ST franchise join, which was working correctly and simply had nothing to match
// against. The E2E fixtures still carried 42 K + 32 DST, so no spec here could reproduce it; the
// `kdstGap` mode serves the board that actually shipped.
//
// ⭐ ALL FOUR CAUSES RENDER IN ONE PAGE, and that is deliberate: the defect was that ONE phrase
// covered all of them, so a spec asserting them one at a time on separate fixtures would not have
// shown the thing that was wrong.
test.describe("an unmatched roster row says WHY", () => {
  const causeOf = (page: Page, name: string) =>
    page
      .locator("tr")
      .filter({ hasText: name })
      .first()
      .getByTestId("unmatched-cell")

  test("a kicker and a defence on a board that published neither read 'not published'", async ({
    page,
  }) => {
    const { errors } = await openMyTeams(page, "kdstGap")

    for (const name of [E2E_ROSTERED_KICKER(), E2E_ROSTERED_DST]) {
      const cell = causeOf(page, name)
      await expect(
        cell,
        `${name} rendered no cause at all — the row is not being classified`,
      ).toBeVisible()
      await expect(
        cell,
        `${name} is on a position the board did not publish, but the surface blamed the name join`,
      ).toHaveAttribute("data-cause", "not-published")
      // ⛔ The exact wording that cost the investigations must be gone from these two cells.
      await expect(cell).toHaveText(/not published/i)
      await expect(cell).not.toHaveText(/^not matched$/i)
    }

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("a name we could not resolve still reads as a name problem", async ({ page }) => {
    // ⭐ THE CONTROL, and the half that makes the test above meaningful: a surface that relabelled
    // EVERY unmatched row "not published" would pass the first test and be just as wrong. WR is a
    // published position, so this row's failure genuinely is the name join.
    const { errors } = await openMyTeams(page, "kdstGap")

    const cell = causeOf(page, E2E_UNMATCHED_ROSTER_NAME)
    await expect(cell).toHaveAttribute("data-cause", "unresolved")
    await expect(cell).toHaveText(/name not matched/i)

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("a position we do not project says so, rather than implying something broke", async ({
    page,
  }) => {
    const { errors } = await openMyTeams(page, "kdstGap")

    const cell = causeOf(page, E2E_ROSTERED_IDP)
    await expect(cell).toHaveAttribute("data-cause", "not-projected")
    await expect(cell).toHaveText(/not projected/i)

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("the card footnote names the missing positions and does not send the user round a loop", async ({
    page,
  }) => {
    // The footnote is where a reader who scanned past the cells finds out what happened. It must
    // name the POSITIONS ("some players are unmatched" is the sentence that hid a two-position
    // outage for a day) and must NOT prescribe a re-import for a gap a re-import cannot fix.
    const { errors } = await openMyTeams(page, "kdstGap")

    const note = page.getByTestId("unmatched-footnote").first()
    await expect(note).toBeVisible()
    await expect(note).toHaveText(/have not published/i)
    await expect(note).toHaveText(/\bK\b|kicker/i)
    await expect(note).toHaveText(/DST|D\/ST|defence|defense/i)
    // ⚠️ SCOPED TO THE not-published CLAUSE, not the whole footnote. This roster carries an
    // unresolved row TOO, and for that one "re-importing usually fixes those" is the correct and
    // useful advice — a blanket scan over the footnote would forbid the sentence that helps, which
    // is the negation-blind failure this suite has already paid for once. What must hold is that
    // the clause about the UNPUBLISHED positions owns the gap and sends nobody round a loop.
    const text = await note.innerText()
    const notPublished = text.slice(text.search(/we have not published/i)).split(/(?<=\.)\s/)[0]
    expect(notPublished, "the not-published clause did not render").toMatch(/have not published/i)
    expect(
      notPublished,
      "the footnote tells the user to re-import to fix a position we never published",
    ).not.toMatch(/usually fixes/i)
    expect(
      notPublished,
      "the footnote does not say that a re-import will NOT fill this gap",
    ).toMatch(/will not fill it/i)

    const forbidden = forbiddenPhrasesIn(await note.innerText())
    expect(forbidden, `denylisted phrasing in the unmatched footnote: ${forbidden.join(", ")}`)
      .toEqual([])

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })
})
