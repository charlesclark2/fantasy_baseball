import { expect, test, type Page } from "@playwright/test"
import { collectPageErrors, mockApi, type MockOptions } from "../support/api-mock"
import { expectNoPageErrors } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"

/**
 * NF-INJ-NEWS-1 — THE REPORTED-ABSENCE STAMP, at the render level.
 *
 * THE MECHANISM. Our availability discount fires on a FORMAL roster transaction (IR/PUP/NFI/
 * suspension) and on nothing else, so a player credibly reported to miss two months while carrying
 * no formal tag is projected as if healthy. NF-INJ-NEWS-1 lets an operator lower that player's
 * projected games BY HAND, with a source URL attached, and stamps the affected rows so the reader
 * can see the adjustment and check the citation.
 *
 * ⭐ WHY THIS NEEDS A BROWSER, given the Python suite already exists. That suite proves the copy is
 * honest, the cap is disjoint from the formal path and the payload stamps only what was applied.
 * None of those is a property a READER has, and every one is satisfied by a page that renders
 * nothing at all:
 *
 *   1. THE CHIP MUST APPEAR ON THE STAMPED ROWS AND ONLY THOSE. A component rendering on every row
 *      is decoration; one rendering on none leaves a hand-adjusted number silently undisclosed —
 *      strictly worse than not having the mechanism, because a reader trusts an unmarked number as
 *      model output. Both are green in `tsc` and in every source scan.
 *   2. ⭐⭐ THE CITATION MUST BE REACHABLE. The single thing separating this mechanism from a guess
 *      is that a reader can go and read what we read. A chip that opens onto a disclaimer with no
 *      working link asserts a manual adjustment while withholding the only evidence for it.
 *   3. THE HONESTY LINES MUST ACTUALLY RENDER. "This is a manual judgment, not a model output" is
 *      the sentence that stops a hand adjustment being read as a projection, and a caveat that
 *      exists only in a constants file has not been disclosed to anybody.
 *   4. THE BOARD-LEVEL NOTE MUST RENDER FROM THE MANIFEST COUNT. A mechanism that announces itself
 *      only on the rows it touched is VISIBLE, not DISCLOSED — a reader who never hovers the right
 *      player has no way to learn that some numbers on this board were set by a person.
 *
 * ⛔⛔ THE FIXTURE IS PLANTED, AND IT HAS TO BE. No shipped fixture carries `reportedAbsence` — the
 * curated file ships EMPTY by design — so asserted against them as-is, "no chip on an un-stamped
 * row" would pass on a build where the feature does not exist, and "a chip on a stamped row" would
 * have no row to run on. That is the NF-C4/NF-C6P3 lesson: a fixture that cannot distinguish the
 * correct implementation from the broken one tests neither.
 */

/** ⭐ HIS `g` IS DELIBERATELY LEFT ALONE BY THE FIXTURE, and that is the load-bearing detail.
 *
 *  The motivating row — Jordyn Tyson — sat at 13.6 projected games, ABOVE the availability-flag
 *  threshold, which is precisely why NF-C8's flag never fired on him. If this fixture's stamped row
 *  also carried a flagged games figure, the spec could not tell a correct implementation from one
 *  nested inside `AvailabilityFlag` — and a nested one would miss exactly the player the story was
 *  written for. Independence has to be in the fixture, not just in the code. */
const STAMPED = {
  name: "Jonathan Taylor",
  id: "00-0036223",
  sourceUrl: "https://example.com/beat-report-absence",
  enteredAt: "2026-08-23",
}
/** Untouched: the key is ABSENT, which is the state of ~every row on a real board. Renders nothing. */
const UNSTAMPED = { name: "Zay Jones", id: "00-0033891" }

/** Located by ACCESSIBLE NAME, not by class or colour — that is what a screen reader gets and what
 *  a colour-blind reader depends on, and the three injury chips on this board are distinguished
 *  visually by hue, which is exactly the distinction such a reader cannot make. */
const CHIP = /reported absence/i

function withReportedAbsence(count = 1, extra?: Partial<MockOptions>): MockOptions {
  return {
    ...extra,
    transform: (pathname, body) => {
      const patch = (p: any) =>
        p?.id === STAMPED.id
          ? { ...p, reportedAbsence: { sourceUrl: STAMPED.sourceUrl, enteredAt: STAMPED.enteredAt } }
          : p
      if (pathname === "/fantasy/nfl/board" && Array.isArray(body)) return body.map(patch)
      if (pathname.startsWith("/fantasy/nfl/projections") && Array.isArray(body?.players)) {
        return { ...body, players: body.players.map(patch) }
      }
      // ⚠️ THE MANIFEST TOO. The board-level disclosure reads its count from here, so a transform
      // covering only the player rows would leave clause 4 asserting against a page that renders
      // nothing — passing for the wrong reason.
      if (pathname === "/fantasy/nfl/manifest" && body && typeof body === "object") {
        return { ...body, reportedAbsenceCount: count }
      }
      return extra?.transform ? extra.transform(pathname, body) : body
    },
  }
}

async function rowFor(page: Page, playerName: string) {
  await page.getByPlaceholder("Search player").fill(playerName)
  const row = page.locator("table tbody tr", { hasText: playerName }).first()
  await expect(row).toBeVisible()
  return row
}

async function gotoTable(page: Page, path: string) {
  await page.goto(path)
  // ⚠️ Wait for FETCHED content — a snapshot taken straight after `goto` can capture the loading
  // state, where every row is legitimately absent, and the spec then reports a product defect for
  // its own race (the CI-only flake NF-TR1 had to fix).
  await expect(page.locator("table tbody tr").first()).toBeVisible()
}

test.describe("the reported-absence stamp — which rows carry it, and what it shows", () => {
  for (const [surface, path] of [
    ["Rankings", "/fantasy/rankings"],
    ["Projections", "/fantasy/projections"],
  ] as const) {
    test(`${surface}: the stamp renders on the stamped row and on no other`, async ({ page }) => {
      // ⭐ BOTH ROWS ARE THE TEST, in one render against one board. Presence alone is satisfied by a
      // component that renders everywhere; absence alone by one that renders nowhere.
      const errors = collectPageErrors(page)
      await mockApi(page, withReportedAbsence())
      await gotoTable(page, path)

      const stamped = await rowFor(page, STAMPED.name)
      await expect(
        stamped.getByRole("button", { name: CHIP }),
        `${STAMPED.name} is served a reportedAbsence stamp and renders nothing — his games figure ` +
          "was lowered by hand and the reader is not told",
      ).toBeVisible()

      const plain = await rowFor(page, UNSTAMPED.name)
      await expect(
        plain.getByRole("button", { name: CHIP }),
        `${UNSTAMPED.name} carries no stamp and renders one anyway — the chip is decoration, and ` +
          "a reader cannot tell which numbers were actually hand-adjusted",
      ).toHaveCount(0)

      expectNoPageErrors(errors)
    })
  }

  test("the disclaimer opens and carries a working link to the source", async ({ page }) => {
    // ⭐⭐ CLAUSE 2 — THE CITATION. Everything separating an operator judgment from a guess is that
    // somebody can go and read the same report. `InfoTip` is Popover-based (not a Radix Tooltip)
    // precisely so a TAP can open it — a source scan sees `<InfoTip>` either way, and only a real
    // click tells them apart. A chip whose disclaimer cannot be opened is worse than no chip.
    await mockApi(page, withReportedAbsence())
    await gotoTable(page, "/fantasy/rankings")
    const row = await rowFor(page, STAMPED.name)
    await row.getByRole("button", { name: CHIP }).click()

    const link = page.getByRole("link", { name: /read the report/i }).first()
    await expect(link, "the stamp opens with no link to the source it claims to have").toBeVisible()
    await expect(link).toHaveAttribute("href", STAMPED.sourceUrl)
    // ⛔ A cross-origin link out of a paid surface must not hand the target a `window.opener`
    // handle, and must not pass our ranking on as an endorsement of the outlet.
    const rel = (await link.getAttribute("rel")) ?? ""
    expect(rel, "the outbound citation is missing noopener").toContain("noopener")

    // CLAUSE 3 — both honesty lines, rendered, not merely defined. These are the sentences that
    // stop a hand adjustment being read as a model output or as a medical opinion.
    await expect(page.getByText(/manual judgment, not a model output/i)).toBeVisible()
    await expect(page.getByText(/not a medical opinion and not a return date/i)).toBeVisible()
  })

  test("the board-level note discloses the mechanism from the manifest count", async ({ page }) => {
    // ⭐ CLAUSE 4. A hand-adjusted number that announces itself only where it was applied is
    // visible, not disclosed — a reader scrolling the board would never learn the mechanism exists.
    await mockApi(page, withReportedAbsence(3))
    await gotoTable(page, "/fantasy/rankings")
    await expect(page.getByText(/lowered by hand/i).first()).toBeVisible()
    await expect(page.getByText(/has not been tested against outcomes/i).first()).toBeVisible()
  })

  test("a board with no overrides discloses nothing — and renders no chips", async ({ page }) => {
    // ⭐ THE ROLLBACK STATE, asserted rather than assumed, and it is the state EVERY board is in
    // today (the curated file ships empty). `0` is a real answer from the manifest, but the note's
    // own sentence — "a small number of players carry..." — is FALSE on a board where none do, so
    // silence is the honest render. This is also what makes the clauses above non-vacuous: without
    // it, a component that renders unconditionally would pass every presence assertion.
    await mockApi(page, {
      transform: (pathname, body) =>
        pathname === "/fantasy/nfl/manifest" && body && typeof body === "object"
          ? { ...body, reportedAbsenceCount: 0 }
          : body,
    })
    await gotoTable(page, "/fantasy/rankings")
    await expect(page.getByRole("button", { name: CHIP })).toHaveCount(0)
    await expect(page.getByText(/lowered by hand/i)).toHaveCount(0)
  })

  test("no copy on the stamp overclaims", async ({ page }) => {
    // The denylist mirror, on the rendered page rather than on the constants file — the same
    // discipline `weekly-designation.spec.ts` applies, for the same reason: copy is only honest
    // where a reader meets it.
    await mockApi(page, withReportedAbsence())
    await gotoTable(page, "/fantasy/rankings")
    await (await rowFor(page, STAMPED.name)).getByRole("button", { name: CHIP }).click()
    const text = (await page.locator("body").innerText()).toLowerCase()
    expect(forbiddenPhrasesIn(text), "the reported-absence surface carries a forbidden claim")
      .toEqual([])
  })
})
