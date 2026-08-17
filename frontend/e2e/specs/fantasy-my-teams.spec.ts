import { expect, test, type Page } from "@playwright/test"
import {
  E2E_LINKED_LEAGUES,
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
  PORTFOLIO_NOTE,
  PORTFOLIO_TOTAL_LABEL,
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
  leagues: "linked" | "none" | "one" | "drafted" = "linked",
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

  /** The headline total on one card. */
  async function teamTotal(page: Page, leagueName: string): Promise<number> {
    const cell = leagueCard(page, leagueName).getByTestId("team-total-value")
    await expect(cell, `${leagueName} rendered no team total`).toBeVisible()
    const text = (await cell.innerText()).trim()
    const value = Number(text.replace(/,/g, ""))
    expect(Number.isFinite(value), `${leagueName}'s total rendered as "${text}"`).toBe(true)
    return value
  }

  test("each team's total is exactly the sum of the starters shown on its own card", async ({
    page,
  }) => {
    const { errors, mock } = await openMyTeams(page)

    for (const league of [E2E_LINKED_LEAGUES.half, E2E_LINKED_LEAGUES.standard]) {
      const points = await starterPoints(page, league.name)
      const total = await teamTotal(page, league.name)
      const sum = points.reduce((a, b) => a + b, 0)

      // Tolerance 0.06: the server rounds each player's points to one decimal and the total is
      // rendered to one decimal, so these should agree exactly — the allowance is for float noise,
      // not for a genuine difference. Anything larger would stop the check being arithmetic.
      expect(
        Math.abs(total - sum),
        `${league.name} shows a total of ${total} over starters worth ${points.join(" + ")} = ` +
          `${sum.toFixed(1)}. A total that includes the bench, or that fields our optimizer's ` +
          `lineup instead of the platform's starters, lands here.`,
      ).toBeLessThanOrEqual(0.06)
    }

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
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

    const half = await teamTotal(page, E2E_LINKED_LEAGUES.half.name)
    const standard = await teamTotal(page, E2E_LINKED_LEAGUES.standard.name)
    expect(
      Math.abs(half - standard - expectedGap),
      `the two teams totalled ${half} and ${standard}; with ${expectedGap.toFixed(1)} of ` +
        `reception scoring between them the gap should be ${expectedGap.toFixed(1)}. A gap of 0 ` +
        `means both were totalled on ONE board and the rows merely relabelled.`,
    ).toBeLessThanOrEqual(0.11)

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

    // The number must never appear without the label that says what it measures.
    await expect(summary).toContainText(PORTFOLIO_TOTAL_LABEL)

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

