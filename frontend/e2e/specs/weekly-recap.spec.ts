import { expect, test } from "@playwright/test"
import {
  E2E_RANKING_BASIS,
  E2E_RECAP_ESPN_DETAIL,
  E2E_RECAP_GAP_NOTE,
  collectPageErrors,
  mockApi,
} from "../support/api-mock"
import { signIn } from "../support/session"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"

/**
 * NF-WK-RC1 Phase B — the weekly recap + standings, asserted in a browser.
 *
 * ══ WHY THESE CLAUSES CANNOT BE PYTHON TESTS ══════════════════════════════════════════════════
 *
 * Everything here is about what a READER SEES. The server already has 30 guards on what it computes
 * and 24 RED-proven breaks; none of them can see a correct payload rendered so that the league's
 * published total and our slot breakdown read as two estimates of one number, or a caveat drawn
 * beside two identical figures. The repo's own rule is that a frontend guard asserting on SOURCE
 * tests that someone typed a string (NF-C4), so every clause below reads rendered text or computed
 * layout.
 *
 * ══ THE CLAUSE THIS FILE EXISTS FOR ═══════════════════════════════════════════════════════════
 *
 * `the disclosure is absent when the itemisation matches`. #1155 shipped a note keyed on the league
 * CAPTURING a term rather than on a MEASURED gap, so it contradicted two identical numbers printed
 * beside it — and the PM has since made that distinction binding on every disclosure this program
 * ships. ⛔ A suite with only the positive clause ("the note renders") is satisfied by that exact
 * defect, which is why `recap: "finalNoGap"` exists as a first-class harness mode.
 */

const LEAGUE = "/fantasy/my-league"

test.describe("weekly recap", () => {
  test("a completed week renders its slots, and the two totals are DIFFERENT FACTS", async ({
    page,
  }) => {
    const errors = collectPageErrors(page)
    const mock = await mockApi(page, { entitlement: "free", leagues: "one", recap: "final" })
    await signIn(page)
    await page.goto(LEAGUE)

    // ⚠️ AN EXPLICIT TESTID, not a text-shaped `div` filter. `locator("div").filter(...).last()`
    // resolves to the INNERMOST matching div, which is a different element on every layout tweak —
    // a selector that fails for reasons unrelated to the property under test teaches a reader to
    // loosen the assertion rather than read it.
    const teamCard = page.getByTestId("recap-team-1")
    await expect(teamCard).toBeVisible()

    // ⭐ BOTH TOTALS PRESENT, AND LABELLED AS DIFFERENT THINGS (PM ruling (i)). The failure this
    // guards is not a missing number — it is ONE number, or two under the same label, which is
    // exactly "presented as two estimates of one number".
    await expect(teamCard.getByText("League total", { exact: true })).toBeVisible()
    await expect(teamCard.getByText("Our slot breakdown", { exact: true })).toBeVisible()
    await expect(teamCard.getByText("45.70", { exact: true })).toBeVisible()
    await expect(teamCard.getByText("43.70", { exact: true })).toBeVisible()

    // The slot breakdown itself — scoped to THIS team's card, because both teams field the same
    // fixture names and an unscoped match is a strict-mode violation rather than a finding.
    await expect(teamCard.getByText("Recap Quarterback")).toBeVisible()
    await expect(teamCard.getByText("24.50")).toBeVisible()

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("the D/ST seat states WHOSE number it is, in the open", async ({ page }) => {
    await mockApi(page, { entitlement: "free", leagues: "one", recap: "final" })
    await signIn(page)
    await page.goto(LEAGUE)

    await expect(page.getByText("Lions D/ST").first()).toBeVisible()
    // ⛔ "not a footnote" (PM disposition D2 = (C)) — the provenance is VISIBLE beside the seat,
    // not hidden behind a tooltip alone. `toBeVisible` is the assertion that distinguishes those.
    await expect(page.getByText("Your league's figure").first()).toBeVisible()
    // …and OUR seats say so too, or "whose number is this" is unanswerable for the other eight.
    await expect(page.getByText("Scored by us").first()).toBeVisible()
  })

  test("an absent player renders a sentence, never a zero", async ({ page }) => {
    await mockApi(page, { entitlement: "free", leagues: "one", recap: "final" })
    await signIn(page)
    await page.goto(LEAGUE)

    // ⚠️ "was not in the game" and "played and scored nothing" are different facts. A 0.00 in this
    // cell states the wrong one, and the reader has no way to tell.
    await expect(
      page.getByText("no stat line was recorded for him this week", { exact: false }).first(),
    ).toBeVisible()
    const receiverRow = page.locator("tr", { hasText: "Recap Receiver" })
    await expect(receiverRow).toHaveCount(0)
  })

  test("the itemisation disclosure renders ADJACENT to the total it is about", async ({ page }) => {
    await mockApi(page, { entitlement: "free", leagues: "one", recap: "final" })
    await signIn(page)
    await page.goto(LEAGUE)

    const note = page.getByText(E2E_RECAP_GAP_NOTE).first()
    await expect(note).toBeVisible()

    // ⭐ ADJACENCY IS A LAYOUT CLAIM, SO IT IS MEASURED (MT1 ruling ③ — "not a panel, not a
    // footnote"). The note must sit inside the same team card as the total, and within it rather
    // than at the bottom of the page: a page-level caveat is the shape the ruling refuses.
    const cardBox = await page.getByTestId("recap-team-1").boundingBox()
    const noteBox = await note.boundingBox()
    expect(cardBox).not.toBeNull()
    expect(noteBox).not.toBeNull()
    expect(noteBox!.y).toBeGreaterThanOrEqual(cardBox!.y)
    expect(noteBox!.y + noteBox!.height).toBeLessThanOrEqual(cardBox!.y + cardBox!.height + 1)
  })

  test("⛔ the disclosure is ABSENT when the itemisation actually matches (#1155)", async ({
    page,
  }) => {
    await mockApi(page, { entitlement: "free", leagues: "one", recap: "finalNoGap" })
    await signIn(page)
    await page.goto(LEAGUE)

    // The week still renders…
    await expect(page.getByText("The Dad Bods").first()).toBeVisible()
    // …and the two totals now MATCH, which is precisely when a "they don't add up" caveat
    // contradicts the numbers printed beside it.
    const body = await page.locator("body").innerText()
    expect(body).not.toContain("don't add up")
    expect(body).not.toContain(E2E_RECAP_GAP_NOTE)
  })

  test("a partial week says so before any number is read", async ({ page }) => {
    await mockApi(page, { entitlement: "free", leagues: "one", recap: "partial" })
    await signIn(page)
    await page.goto(LEAGUE)

    await expect(page.getByText("Still in progress").first()).toBeVisible()
    await expect(
      page.getByText("had not finished when these figures were recorded", { exact: false }).first(),
    ).toBeVisible()
  })

  test("standings render with the arithmetic that produced the order", async ({ page }) => {
    await mockApi(page, { entitlement: "free", leagues: "one", recap: "final" })
    await signIn(page)
    await page.goto(LEAGUE)

    await expect(page.getByRole("heading", { name: "Standings" })).toBeVisible()
    await expect(page.getByText("Points for", { exact: true })).toBeVisible()
    await expect(page.getByText("Points against", { exact: true })).toBeVisible()
    // ⭐ "no opaque composite score" — the order must be reproducible by hand from what is shown.
    await expect(page.getByText(E2E_RANKING_BASIS)).toBeVisible()
    // …and WHICH weeks are in the totals, because a week we could not read is skipped, not zeroed.
    await expect(page.getByText("Totals cover week 1.")).toBeVisible()
  })

  test("a week that played but is not recorded yet says exactly that", async ({ page }) => {
    await mockApi(page, { entitlement: "free", leagues: "one", recap: "notRecorded" })
    await signIn(page)
    await page.goto(LEAGUE)

    // ⛔ NOT A BLANK. The server's own sentence names the WEEK — a different fact from a platform
    // we cannot read, and from a week that has not been played.
    await expect(
      page.getByText("have not recorded week 1's player statistics yet", { exact: false }).first(),
    ).toBeVisible()
  })

  test("a platform whose weeks we cannot read says STANDINGS specifically", async ({ page }) => {
    await mockApi(page, {
      entitlement: "free",
      leagues: "one",
      recap: "platformUnavailable",
    })
    await signIn(page)
    await page.goto(LEAGUE)

    const shown = page.getByText(E2E_RECAP_ESPN_DETAIL).first()
    await expect(shown).toBeVisible()
    // ⭐ THE WORD IS THE RULING (PM ruling (i), amendment 2): a platform we cannot fetch has NO
    // standings, rather than approximate ones. A message that said only "recap" would leave a
    // reader expecting standings to appear elsewhere.
    expect(await shown.innerText()).toContain("standings")
  })

  test("the rendered recap makes no forbidden claim and no imperative", async ({ page }) => {
    await mockApi(page, { entitlement: "free", leagues: "one", recap: "final" })
    await signIn(page)
    await page.goto(LEAGUE)
    await expect(page.getByText("The Dad Bods").first()).toBeVisible()

    const body = await page.locator("body").innerText()
    expect(forbiddenPhrasesIn(body)).toEqual([])

    // ⛔ SPEC BOUNDARY (ii): the recap states what scored, never what the reader ought to have done.
    // A start/sit imperative on a FACTUAL surface is a decision claim wearing a fact's clothes.
    for (const phrase of [
      "should have started",
      "you should",
      "start him",
      "sit him",
      "must start",
    ]) {
      expect(body.toLowerCase()).not.toContain(phrase)
    }
  })
})
