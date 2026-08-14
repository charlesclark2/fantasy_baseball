import { expect, test, type Page } from "@playwright/test"
import {
  E2E_LINKED_LEAGUES,
  E2E_UNMATCHED_ROSTER_NAME,
  collectPageErrors,
  linkedRosterSubject,
  mockApi,
} from "../support/api-mock"
import { signIn } from "../support/session"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"

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

async function openMyTeams(page: Page, leagues: "linked" | "none" | "one" = "linked") {
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

