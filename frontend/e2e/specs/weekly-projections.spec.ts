import { expect, test, type Page } from "@playwright/test"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { collectPageErrors, mockApi, type MockOptions } from "../support/api-mock"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"
import { signIn } from "../support/signed-in"
import {
  WEEKLY_NUMBERS_WITHHELD,
  WEEKLY_WITHHELD_SINCE,
  weeklyRowOrder,
  weeklyRowView,
} from "@/lib/weekly-suppression"
import { WEEKLY_PAGE_STANDFIRST, WEEKLY_WITHHELD_NOTE } from "@/lib/fantasy-claim-copy"

/**
 * NF-WK-FE1 — THE WEEKLY PROJECTIONS SURFACE, AT THE RENDER LEVEL.
 *
 * ⭐ EVERY ASSERTION HERE READS THE DOM THE BROWSER PRODUCED. NF-C4 measured eight frontend defects
 * that were all green in CI because the suite asserted on SOURCE — a guard that greps a component,
 * or walks a className, tests that somebody TYPED a string. Nothing below reads this repo's source,
 * and every number checked is read from the FIXTURE'S OWN VALUES rather than typed here, so a
 * re-capture moves the expectation with the payload instead of turning the suite red for the wrong
 * reason.
 *
 * ══ THE FIVE THINGS THAT COULD GO WRONG SILENTLY ════════════════════════════════════════════════
 *
 *  1. A POINT COULD RENDER WITHOUT ITS BAND. That is not a cosmetic loss — a weekly point is a mean
 *     over a wide distribution, and printing it alone overstates precision on the one surface where
 *     a reader is most likely to act on it. The band clause is per-ROW, not page-wide: a count
 *     cannot tell "every point carries its interval" from "some of them do" (the lesson
 *     `expectLockChipInEveryRow` records).
 *
 *  2. A BYE COULD RENDER AS A GAP. A bye is a DETERMINISTIC zero knowable at schedule release, and
 *     an em-dash where its zero belongs says "we have nothing for this player" — a different, false
 *     fact. Its row must show the zero AND keep its rest-of-season number, which is unaffected.
 *
 *  3. THE PRE-PUBLISH STATE COULD LOOK BROKEN. Measured on the live API 2026-09-13, both free
 *     weekly routes answer 404 — the ordinary state of this surface between builds. It must render
 *     as a STATED absence, never a spinner and never an error, and it must be distinguishable from
 *     a genuine read failure, because those two send the next investigation to different places.
 *
 *  4. THE PAID SUBSTRATE COULD PRINT FOR A FREE CALLER. The gate is WHICH COMPONENT PRINTS (#681
 *     gated one of three renderers and looked complete), so the clause is proven BOTH WAYS: a free
 *     render carries no paid value anywhere in its text, and an entitled render carries them.
 *
 *  5. THE STAT LINE COULD BECOME A SECOND TOTAL. The points head and the component head are
 *     INDEPENDENT models — scoring the line does not reproduce the point. This page therefore never
 *     sums the line, and the clause below asserts that no total appears beside it.
 *
 * ══ NF-INC-0916 — WHY SEVERAL CLAUSES BELOW BRANCH ON A FLAG ════════════════════════════════════
 *
 * The weekly model's training feeds were never ingested, so it fitted a week of fabricated zeros
 * and its served point runs at a fraction of realized scoring. Until it is retrained, the page
 * WITHHOLDS every number the fit produced. The reversal is one constant
 * (`WEEKLY_NUMBERS_WITHHELD`), and these clauses read that same constant so the flip carries the
 * suite with it — a suite that had to be rewritten alongside the reversal would make the reversal
 * a rebuild rather than the two-line change it is designed to be.
 *
 * ⛔ NOT `test.skip`. A conditionally-skipped clause is a vacuous anchor with a plausible excuse
 * attached (NF1.7 (a)); every test below is DECLARED LIVE and branches INSIDE its body, so exactly
 * one branch runs and neither can be silently lost. The branch that is not running in this build is
 * covered unconditionally by the pure clauses in section 0, which drive `weeklyRowView` BOTH ways —
 * and section 0's last clause pins the RENDERED page to that same function, so the two compose into
 * coverage of the reversal instead of each proving something about a different decision.
 */

const FIXTURE_DIR = join(process.cwd(), "e2e", "fixtures", "api")
const readFixture = (name: string) => JSON.parse(readFileSync(join(FIXTURE_DIR, name), "utf8"))

const MANIFEST = readFixture("fantasy-nfl-weekly-manifest.synthetic.json")
const FREE = readFixture("fantasy-nfl-weekly-players-free.synthetic.json")
const ENTITLED = readFixture("fantasy-nfl-weekly-players-entitled.synthetic.json")

const WEEKLY_URL = "/fantasy/weekly"

type Player = (typeof FREE)["players"][number]

/** The fixture's own bye row / rookie row / final-week row, found by the PROPERTY each clause is
 *  about rather than by name. ⚠️ Each is asserted to exist before it is used: a clause that needed
 *  one and found none would be passing on nothing (NF1.7 (a)). */
const byeRow: Player = FREE.players.find((p: Player) => p.status === "bye")
const rookieRow: Player = FREE.players.find((p: Player) => p.histWeeks === 0)
const finalWeekRow: Player = FREE.players.find((p: Player) => p.rosPpr === null)
const projectedRow: Player = FREE.players.find((p: Player) => p.status === "projected")

test("the weekly fixture reaches every state the page distinguishes", () => {
  // The suite's own non-vacuity check, first and separately: if the fixture stopped carrying one of
  // these shapes, the clause that names it below would pass against a page that never rendered it.
  expect(byeRow, "no bye row in the fixture — the bye clauses would assert on nothing").toBeTruthy()
  expect(rookieRow, "no histWeeks=0 row — the evidence-base clause would assert on nothing").toBeTruthy()
  expect(finalWeekRow, "no null-ros row — the declared-null clause would assert on nothing").toBeTruthy()
  expect(projectedRow, "no projected row at all").toBeTruthy()
  expect(FREE.players.length).toBeGreaterThan(3)
})

async function openWeekly(page: Page, options: MockOptions = {}) {
  const errors = collectPageErrors(page)
  const mock = await mockApi(page, options)
  await page.goto(WEEKLY_URL)
  return { mock, errors }
}

/** One decimal, the way the page formats a number — so an expectation is written in the units the
 *  DOM actually carries rather than in the fixture's raw precision. */
const oneDp = (v: number) => v.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })

// ══ 0 — NF-INC-0916: THE WITHHOLDING, AND ITS REVERSAL ══════════════════════════════════════════
//
// ⭐ THE PURE HALF, DRIVEN BOTH WAYS UNCONDITIONALLY. `weeklyRowView` takes `withheld` as a
// PARAMETER rather than reading the constant, precisely so both branches are reachable in one
// build — a function whose branch is baked in can only ever be tested one way, which is how a
// reversal ships broken.

test("withheld, every model-produced cell is withheld — and nothing else is", () => {
  expect(FREE.players.length, "no rows — these clauses would pass on nothing").toBeGreaterThan(3)
  for (const p of FREE.players as Player[]) {
    const v = weeklyRowView(p, true)
    for (const [name, cell] of Object.entries(v)) {
      if (name === "band" || name === "statLine") {
        expect(cell, `${name} must be off while the numbers are withheld`).toBe(false)
        continue
      }
      expect((cell as { kind: string }).kind, `${name} leaked a value for ${p.id}`).toBe("withheld")
    }
  }
})

test("un-withheld, every cell carries the payload's own number verbatim", () => {
  // ⭐ THE REVERSAL'S ACTUAL CONTRACT: flipping the constant must restore the page EXACTLY, not
  // approximately. Read from the FIXTURE'S values, so a re-capture moves the expectation with the
  // payload rather than turning this red for the wrong reason.
  for (const p of FREE.players as Player[]) {
    const v = weeklyRowView(p, false)
    expect(v.point).toEqual({ kind: "value", n: p.fpPpr })
    expect(v.p10).toEqual({ kind: "value", n: p.fpP10 })
    expect(v.p90).toEqual({ kind: "value", n: p.fpP90 })
    expect(v.band).toBe(true)
    expect(v.statLine).toBe(true)
    // ⚠️ A DECLARED NULL STAYS DECLARED. The season's final week has no remaining horizon to sum,
    // which is a different fact from a withheld number and from a zero — three states, three
    // renderings, and collapsing any two is the error this surface is built to avoid.
    expect(v.ros).toEqual(p.rosPpr == null ? { kind: "absent" } : { kind: "value", n: p.rosPpr })
  }
  expect(
    (FREE.players as Player[]).some((p) => p.rosPpr == null),
    "no null-ros row in the fixture — the declared-null half of this clause would pass on nothing",
  ).toBe(true)
})

test("the ordering carries no model quantity while the numbers are withheld, and is restored by the same flag", () => {
  const byPoints = (a: Player, b: Player) => b.fpPpr - a.fpPpr || a.id.localeCompare(b.id)
  // Un-withheld: the flag hands back the points comparator UNCHANGED — the reversal does not have
  // to remember the ordering separately.
  expect(weeklyRowOrder(false, byPoints)).toBe(byPoints)

  const withheldOrder = [...(FREE.players as Player[])].sort(weeklyRowOrder(true, byPoints))
  const pointsOrder = [...(FREE.players as Player[])].sort(byPoints)
  // Position, then name — and demonstrably NOT the model's order.
  const positions = withheldOrder.map((p) => p.pos)
  expect([...positions].sort()).toEqual(positions)
  expect(
    withheldOrder.map((p) => p.id),
    "the withheld order is identical to the points order — the fixture cannot tell them apart, so this clause proves nothing",
  ).not.toEqual(pointsOrder.map((p) => p.id))
})

test("the page renders exactly what the row plan says, cell by cell", async ({ page }) => {
  // ⭐⭐ THE LINK THAT MAKES THE COMPOSITION REAL. The clauses above prove `weeklyRowView` is right
  // in both branches; this proves the PAGE renders that function's output rather than deciding
  // again. Without it the two halves would be about different things and the pair would prove
  // nothing about the reversal.
  await openWeekly(page)
  const rows = page.locator('[data-testid="weekly-row"]')
  await expect(rows.first()).toBeVisible()

  for (const p of (FREE.players as Player[]).slice(0, 5)) {
    const plan = weeklyRowView(p, WEEKLY_NUMBERS_WITHHELD)
    const row = page.locator(`[data-testid="weekly-row"][data-player-id="${p.id}"]`)
    const marker = row.locator('[data-testid="weekly-points"] [data-withheld]')
    if (plan.point.kind === "withheld") {
      await expect(marker, `${p.id} should render a withheld marker`).toHaveCount(1)
      const cellText = await row.locator('[data-testid="weekly-points"]').innerText()
      expect(cellText).not.toContain(oneDp(p.fpPpr))
    } else {
      await expect(marker, `${p.id} renders a withheld marker but the plan says it has a value`).toHaveCount(0)
      expect(await row.locator('[data-testid="weekly-points"]').innerText()).toContain(oneDp(p.fpPpr))
    }
    // The bar is a drawing of the same distribution, so it travels with the numbers.
    await expect(row.locator('[data-testid="weekly-band-bar"]')).toHaveCount(plan.band ? 1 : 0)
  }
})

test("no weekly model number reaches the DOM while they are withheld", async ({ page }) => {
  // ⭐ THE LEAK CHECK, mirroring the paid one below. A per-cell assertion cannot see a number that
  // escaped through a title attribute, an aria label or a chart; this reads the whole rendered text.
  // ⚠️ TOKENS, NOT SUBSTRINGS — the same correction the paid clause records: a substring form
  // reports a leak whenever a model figure happens to sit inside an unrelated free number.
  await openWeekly(page)
  await expect(page.locator('[data-testid="weekly-row"]').first()).toBeVisible()

  const modelValues = new Set<string>()
  for (const p of FREE.players as Player[]) {
    for (const v of [p.fpPpr, p.fpP10, p.fpP90, p.rosPpr, p.rosP10, p.rosP90]) {
      // A zero is not distinctive — a bye's identity zero and a withheld cell are different facts,
      // and a page full of legitimate small integers would make this clause fire on nothing real.
      if (typeof v === "number" && v > 0) modelValues.add(oneDp(v))
    }
  }
  expect(modelValues.size, "no model values in the fixture — this clause would pass on nothing").toBeGreaterThan(5)

  const tokens = await renderedNumericTokens(page)
  const leaked = [...modelValues].filter((v) => tokens.has(v))
  if (WEEKLY_NUMBERS_WITHHELD) {
    expect(leaked, `weekly model value(s) rendered while withheld: ${leaked.join(", ")}`).toEqual([])
  } else {
    // The other direction: with the withholding lifted these numbers MUST be on the page, or this
    // clause would go on passing after a reversal that quietly rendered nothing.
    expect(leaked.length, "the withholding is lifted but no model value is rendered").toBeGreaterThan(5)
  }
})

test("the notice says what broke, carries its date, and promises no delivery date", async ({ page }) => {
  await openWeekly(page)
  const notice = page.locator('[data-testid="weekly-withheld-notice"]')

  if (!WEEKLY_NUMBERS_WITHHELD) {
    // ⭐ THE REVERSAL MUST TAKE THE NOTICE DOWN TOO. A page that restored the numbers and kept
    // telling readers they were withheld is the same defect facing the other way.
    await expect(notice).toHaveCount(0)
    return
  }

  await expect(notice).toBeVisible()
  const text = await notice.innerText()

  // DATED — a notice a reader can tell is a month old from one that went up this morning.
  expect(text).toContain(WEEKLY_WITHHELD_SINCE)

  // IT NAMES THE CAUSE, rather than describing a schedule. The served prose is the copy module's
  // own, read from it rather than retyped here, so a reword moves the expectation with the copy.
  expect(text).toContain(WEEKLY_WITHHELD_NOTE.mechanism)
  expect(text).toContain(WEEKLY_WITHHELD_NOTE.effect)
  expect(text).toContain(WEEKLY_WITHHELD_NOTE.kept)

  // ⛔ NO EUPHEMISM, and ⛔ NO ETA. Each of these describes a schedule rather than a fact, and each
  // would leave a reader believing the numbers were fine and merely absent.
  const lowered = text.toLowerCase()
  for (const euphemism of [
    "temporarily unavailable", "under maintenance", "undergoing maintenance",
    "making improvements", "check back", "coming soon", "shortly",
  ]) {
    expect(lowered, `the notice uses the euphemism "${euphemism}"`).not.toContain(euphemism)
  }
  // A month name or a weekday would be a delivery commitment made out of an inference.
  expect(lowered).not.toMatch(
    /\b(january|february|march|april|may|june|july|august|september|october|november|december|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/,
  )

  // ⭐⭐ AND THE PAGE MUST NOT MAKE THE CLAIM IT IS WITHDRAWING, TWO LINES ABOVE THE WITHDRAWAL.
  // The ordinary standfirst promises "the 80% range around it and what is left of his season
  // beside it" — precisely what is withheld — and it renders directly under the title. A surface
  // that advertises and retracts the same thing in one screenful reads as carelessness rather than
  // as candour; this is what keeps the two in step through a reversal.
  const body = await page.evaluate(() => document.body.innerText)
  expect(body).not.toContain(WEEKLY_PAGE_STANDFIRST)
})

// ══ 1 — the band renders with the point, EVERYWHERE the point renders ═══════════════════════════

test("every rendered row carries its 80% band beside the point", async ({ page }) => {
  const { mock, errors } = await openWeekly(page)
  const rows = page.locator('[data-testid="weekly-row"]')
  await expect(rows.first()).toBeVisible()

  const total = await rows.count()
  expect(total).toBe(FREE.players.length)

  // PER-ROW, not a page-wide count: a count cannot distinguish "every point carries its interval"
  // from "most of them do", which is exactly the defect this clause exists to catch.
  const withBand = await rows.evaluateAll(
    (els) => els.filter((e) => {
      const band = e.querySelector('[data-testid="weekly-band"]')
      return !!band && /\d/.test(band.textContent ?? "") && (band.textContent ?? "").includes("–")
    }).length,
  )

  if (WEEKLY_NUMBERS_WITHHELD) {
    // ⭐ THE SAME INVARIANT, FACING THE OTHER WAY (NF-INC-0916). The rule is that a point and its
    // band travel together — so with the point withheld, a band on ANY row would be the defect
    // this clause exists to catch, published without the number that gives it meaning.
    expect(withBand, `${withBand} of ${total} rows render a band while the point is withheld`).toBe(0)
    const withMarker = await rows.evaluateAll(
      (els) => els.filter((e) => !!e.querySelector('[data-testid="weekly-points"] [data-withheld]')).length,
    )
    expect(withMarker, `${total - withMarker} of ${total} rows do not say the point is withheld`).toBe(total)
  } else {
    expect(withBand, `${total - withBand} of ${total} rows render a point with no band`).toBe(total)
  }

  expectApiFullyMocked(mock)
  await expectNoNaN(page)
  expectNoPageErrors(errors)
})

test("the band shown is the payload's own p10–p90, not a recomputed one", async ({ page }) => {
  await openWeekly(page)
  const row = page.locator(`[data-testid="weekly-row"][data-player-id="${projectedRow.id}"]`)
  await expect(row).toBeVisible()

  if (WEEKLY_NUMBERS_WITHHELD) {
    // There is no band to check its provenance against. The clause that matters while the numbers
    // are down is that neither endpoint reached the page at all, and section 0 asserts it over the
    // whole DOM rather than over this one cell.
    await expect(row.locator('[data-testid="weekly-band"]')).toHaveCount(0)
    return
  }

  const band = await row.locator('[data-testid="weekly-band"]').innerText()
  // Read from the FIXTURE'S values — a re-capture moves this with the payload.
  expect(band).toContain(oneDp(projectedRow.fpP10))
  expect(band).toContain(oneDp(projectedRow.fpP90))
  const point = await row.locator('[data-testid="weekly-points"]').innerText()
  expect(point).toContain(oneDp(projectedRow.fpPpr))
})

// ══ 2 — a bye is a STATED ZERO, and its rest-of-season is untouched ═════════════════════════════

test("a bye renders as a stated zero, keeps its rest-of-season number, and is not an em-dash", async ({ page }) => {
  await openWeekly(page)
  const row = page.locator(`[data-testid="weekly-row"][data-player-id="${byeRow.id}"]`)
  await expect(row).toBeVisible()

  // ⭐ THE BYE STATUS SURVIVES THE WITHHOLDING (NF-INC-0916), and it is the reason this assertion
  // sits ABOVE the branch: who is not playing is a fact from the schedule, not from the model, so
  // it is on the page in both states.
  await expect(row.locator('[data-testid="weekly-bye-chip"]')).toBeVisible()

  if (WEEKLY_NUMBERS_WITHHELD) {
    // The zero is the MODEL'S cell, so it goes down with the rest — and the bye NOTE goes with it,
    // because that note exists to stop a reader misreading a zero in a column that no longer has
    // one, and it also points at a rest-of-season figure that is itself withheld.
    await expect(row.locator('[data-testid="weekly-points"] [data-withheld]')).toHaveCount(1)
    await expect(page.locator('[data-testid="weekly-bye-note"]')).toHaveCount(0)
    return
  }

  // The ZERO, not a gap. ⚠️ This is the assertion that would go red if a bye fell through to the
  // "we have nothing for this player" em-dash.
  const points = (await row.locator('[data-testid="weekly-points"]').innerText()).trim()
  expect(points).toContain("0.0")
  expect(points).not.toContain("—")

  // …AND the rest-of-season number beside it is the fixture's real one, unaffected by the bye. A
  // page that zeroed it would be making a false claim about the player's remaining season.
  expect(byeRow.rosPpr).toBeGreaterThan(0)
  const ros = await row.locator('[data-testid="weekly-ros"]').innerText()
  expect(ros).toContain(oneDp(byeRow.rosPpr!))

  // The explainer rides with it — a zero in a points column is the most misreadable cell here.
  await expect(page.locator('[data-testid="weekly-bye-note"]')).toBeVisible()
})

test("a final-week row renders its null rest-of-season as an absence, never as a zero", async ({ page }) => {
  await openWeekly(page)
  const row = page.locator(`[data-testid="weekly-row"][data-player-id="${finalWeekRow.id}"]`)
  await expect(row).toBeVisible()
  const ros = (await row.locator('[data-testid="weekly-ros"]').innerText()).trim()

  if (WEEKLY_NUMBERS_WITHHELD) {
    // ⭐ THREE STATES, NOT TWO. A withheld cell must not borrow the declared-null's em-dash: "we
    // have a number and are not showing it" and "there is no number to show" are different facts,
    // and this row is the one place they could be confused, because it is genuinely both-ish.
    await expect(row.locator('[data-testid="weekly-ros"] [data-withheld]')).toHaveCount(1)
    expect(ros).not.toContain("—")
    return
  }

  // ⭐ A DECLARED NULL AND A ZERO ARE DIFFERENT FACTS: "there is no remaining horizon to sum" is
  // not "he will score nothing". Rendering 0.0 here would assert the second.
  expect(ros).toContain("—")
  expect(ros).not.toMatch(/\b0\.0\b/)
})

// ══ 3 — the evidence base is visible ════════════════════════════════════════════════════════════

test("weeks-of-form is rendered per row, and a rookie's zero is shown rather than hidden", async ({ page }) => {
  await openWeekly(page)
  const rookie = page.locator(`[data-testid="weekly-row"][data-player-id="${rookieRow.id}"]`)
  await expect(rookie).toBeVisible()
  // ⭐ The zero must RENDER. A projection standing on position and a rookie flag alone is exactly
  // the row whose thin evidence base a reader needs to see, and a blank cell hides it.
  expect((await rookie.locator('[data-testid="weekly-hist-weeks"]').innerText()).trim()).toBe("0")

  const veteran = page.locator(`[data-testid="weekly-row"][data-player-id="${projectedRow.id}"]`)
  expect((await veteran.locator('[data-testid="weekly-hist-weeks"]').innerText()).trim())
    .toBe(String(projectedRow.histWeeks))
})

// ══ 4 — the absences: three causes, three rows ══════════════════════════════════════════════════

test("every absence reason is named separately, with the served detail verbatim", async ({ page }) => {
  await openWeekly(page)
  const panel = page.locator('[data-testid="weekly-absences"]')
  await expect(panel).toBeVisible()

  const reasons = MANIFEST.absences.filter((a: { n: number }) => a.n > 0)
  expect(reasons.length, "the manifest fixture carries no non-zero absence").toBeGreaterThan(1)

  for (const a of reasons) {
    const row = panel.locator(`[data-testid="weekly-absence-${a.reason}"]`)
    await expect(row, `absence reason ${a.reason} is not rendered`).toBeVisible()
    const text = await row.innerText()
    expect(text).toContain(String(a.n))
    // SERVED PROSE, VERBATIM — a paraphrase here would be claim copy no screening had looked at.
    expect(text).toContain(a.detail)
  }
})

// ══ 5 — the two empty states are DIFFERENT FACTS ════════════════════════════════════════════════

test("a week that has not published renders a stated absence — not a spinner, not an error", async ({ page }) => {
  const { errors } = await openWeekly(page, { weekly: "awaiting" })

  const notice = page.locator('[data-testid="weekly-awaiting-publish"]')
  await expect(notice).toBeVisible()

  // ⛔ NOT an error treatment, and not a loading one. Both would be wrong about whose problem it is.
  await expect(page.locator('[data-testid="weekly-read-failed"]')).toHaveCount(0)
  const body = await page.evaluate(() => document.body.innerText)
  expect(body.toLowerCase()).not.toContain("loading")
  // And the page still explains itself: the PPR framing is above the table and survives the absence.
  await expect(page.locator('[data-testid="weekly-ppr-native"]')).toBeVisible()

  expectNoPageErrors(errors)
})

test("a failed read is stated as OUR problem, and is distinguishable from an unpublished week", async ({ page }) => {
  await openWeekly(page, { weekly: "failed" })
  await expect(page.locator('[data-testid="weekly-read-failed"]')).toBeVisible()
  // ⭐ THE DISCRIMINATION IS THE ASSERTION. If both states rendered the same notice, the next
  // investigation would start in the wrong place — which is the whole reason they are separate.
  await expect(page.locator('[data-testid="weekly-awaiting-publish"]')).toHaveCount(0)
})

// ══ 6 — the PAID gate, proven BOTH WAYS ═════════════════════════════════════════════════════════

/** Every paid VALUE on the fixture's rows, as the page would format it. Built from the entitled
 *  payload so the check cannot drift from what the contract actually withholds. */
function paidValueStrings(): string[] {
  const out = new Set<string>()
  for (const p of ENTITLED.players) {
    for (const [k, v] of Object.entries(p)) {
      if (k === "q" || typeof v !== "number") continue
      if (k in FREE.players[0]) continue // a free field, not a paid one
      if (v === 0) continue // a zero is not distinctive enough to attribute to the paid payload
      out.add(oneDp(v))
    }
  }
  return [...out]
}

/**
 * Every NUMBER the page rendered, as a WHOLE TOKEN.
 *
 * ⚠️⚠️ TOKENS, NOT SUBSTRINGS, AND THIS IS A CORRECTION PAID FOR IN THIS STORY. The first cut asked
 * whether the body TEXT contained each paid value and reported eleven leaks on a page that was
 * correctly gated — every one of them a paid figure appearing INSIDE an unrelated free number
 * ("1.6" inside the free point `11.6`; "0.2" inside the free rest-of-season `200.2`). Measured
 * against the two fixtures: eleven such collisions, and ZERO cases where a paid value equals a free
 * rendered token — so the substring form was pure false-positive and the token form loses no
 * discrimination at all.
 *
 * ⛔ It is NOT a weakening. A real leak renders the paid figure as its own token, which this
 * catches; the red proof drives exactly that (un-gate the panel and this clause must go red).
 */
async function renderedNumericTokens(page: Page): Promise<Set<string>> {
  const body = await page.evaluate(() => document.body.innerText)
  return new Set(body.match(/\d+(?:\.\d+)?/g) ?? [])
}

test("a free caller's rendered page carries no paid stat value anywhere in it", async ({ page }) => {
  const { mock } = await openWeekly(page, { entitlement: "free" })
  await expect(page.locator('[data-testid="weekly-row"]').first()).toBeVisible()

  // Open the detail for a player who HAS a paid line, so the gate is exercised where it matters
  // rather than on a row with nothing to withhold.
  await page.locator(`[data-testid="weekly-row"][data-player-id="${projectedRow.id}"]`)
    .locator('[data-testid="weekly-detail-toggle"]').click()
  if (WEEKLY_NUMBERS_WITHHELD) {
    // ⭐ WITHHELD BEATS LOCKED, and the ordering is the point. The lock says "the points projection
    // and its range on this page are free" — currently false — so showing it here would be a claim
    // about pricing standing in for a claim about correctness.
    await expect(page.locator('[data-testid="weekly-stat-line-withheld"]')).toBeVisible()
    await expect(page.locator('[data-testid="weekly-stat-line-locked"]')).toHaveCount(0)
  } else {
    await expect(page.locator('[data-testid="weekly-stat-line-locked"]')).toBeVisible()
  }
  await expect(page.locator('[data-testid="weekly-stat-line"]')).toHaveCount(0)

  const values = paidValueStrings()
  expect(values.length, "no paid values in the fixture — this clause would pass on nothing").toBeGreaterThan(5)
  const tokens = await renderedNumericTokens(page)
  const leaked = values.filter((v) => tokens.has(v))
  expect(leaked, `paid stat value(s) rendered for a free caller: ${leaked.join(", ")}`).toEqual([])

  // ⭐ AND THE FREE PAYLOAD IS WHAT WAS FETCHED. A page that never asked for the paid half would
  // pass the clause above for the wrong reason.
  expect(mock.requested.some((r) => r.startsWith("/fantasy/nfl/weekly/projections?"))).toBe(true)
  expect(mock.requested.some((r) => r.startsWith("/fantasy/nfl/weekly/projections-full"))).toBe(false)
})

test("an entitled caller sees the projected stat line, and it is never totalled", async ({ page }) => {
  await signIn(page, { groups: ["subscriber"] })
  const { mock } = await openWeekly(page, { entitlement: "entitled" })
  await expect(page.locator('[data-testid="weekly-row"]').first()).toBeVisible()

  await page.locator(`[data-testid="weekly-row"][data-player-id="${projectedRow.id}"]`)
    .locator('[data-testid="weekly-detail-toggle"]').click()

  if (WEEKLY_NUMBERS_WITHHELD) {
    // ⭐ THE STAT LINE IS DOWN FOR AN ENTITLED READER TOO (NF-INC-0916) — it comes from the same
    // fit and carries the same defect, so withholding it only from non-members would be selling a
    // number we have measured wrong. ⛔ And it must NOT render the "no line was produced" sentence,
    // which is a claim about the model that is untrue here.
    await expect(page.locator('[data-testid="weekly-stat-line-withheld"]')).toBeVisible()
    await expect(page.locator('[data-testid="weekly-stat-line"]')).toHaveCount(0)
    await expect(page.locator('[data-testid="weekly-stat-line-absent"]')).toHaveCount(0)
    await expect(page.locator('[data-testid="weekly-stat-line-locked"]')).toHaveCount(0)
    expectApiFullyMocked(mock)
    await expectNoNaN(page)
    return
  }

  const panel = page.locator('[data-testid="weekly-stat-line"]')
  await expect(panel).toBeVisible()
  await expect(page.locator('[data-testid="weekly-stat-line-locked"]')).toHaveCount(0)

  // The PAID values are actually on screen — the other direction of the clause above.
  const paidRow = ENTITLED.players.find((p: Player) => p.id === projectedRow.id)
  const shown = await panel.innerText()
  const present = Object.entries(paidRow)
    .filter(([k, v]) => !(k in FREE.players[0]) && typeof v === "number" && (v as number) > 0)
    .map(([, v]) => oneDp(v as number))
    .filter((v) => shown.includes(v))
  expect(present.length, `no paid stat value rendered for an entitled caller: ${shown}`).toBeGreaterThan(2)

  // ⭐⭐ NEVER A SECOND TOTAL. The points head and the component head are independent models, so a
  // figure derived from this line would not equal the point above it and no reader could reconcile
  // the two. The disclosure rides with the numbers, un-collapsed.
  await expect(page.locator('[data-testid="weekly-stat-line-note"]')).toBeVisible()
  const noteText = await page.locator('[data-testid="weekly-stat-line-note"]').innerText()
  expect(noteText.toLowerCase()).toContain("independently")

  expectApiFullyMocked(mock)
  await expectNoNaN(page)
})

test("an in-flight paid read says so, and does not claim the stat line is absent", async ({ page }) => {
  await signIn(page, { groups: ["subscriber"] })
  // ⭐ DELAY ONLY THE PAID READ, so the page renders its rows normally and the row-detail panel is
  // genuinely mid-fetch when it is opened — which is the real sequence a subscriber hits, not a
  // simulated flag. The free reads are untouched, so nothing else on the page is in a fake state.
  const { mock } = await openWeekly(page, {
    entitlement: "entitled",
    delay: { paths: ["/fantasy/nfl/weekly/projections-full"], ms: 4000 },
  })
  await expect(page.locator('[data-testid="weekly-row"]').first()).toBeVisible()

  await page.locator(`[data-testid="weekly-row"][data-player-id="${projectedRow.id}"]`)
    .locator('[data-testid="weekly-detail-toggle"]').click()

  if (WEEKLY_NUMBERS_WITHHELD) {
    // ⭐ THE SAME RULE, AND THE PANEL SHORT-CIRCUITS BEFORE THE FETCH MATTERS: an in-flight read is
    // irrelevant when the answer is withheld either way, and rendering a spinner would promise a
    // line that is not coming. The negative assertion is still the one that matters — neither the
    // loading sentence nor the "nothing was produced" sentence may appear.
    await expect(page.locator('[data-testid="weekly-stat-line-withheld"]')).toBeVisible()
    await expect(page.locator('[data-testid="weekly-stat-line-loading"]')).toHaveCount(0)
    await expect(page.locator('[data-testid="weekly-stat-line-absent"]')).toHaveCount(0)
    return
  }

  // ⛔ THE ASSERTION THAT MATTERS IS THE NEGATIVE ONE. "No projected stat line was produced for
  // this player" is a claim about the MODEL; rendering it while the fetch is still in flight makes
  // it FALSE for as long as the network takes. A slow render is acceptable, an untrue sentence is
  // not — and the two are indistinguishable to a reader.
  await expect(page.locator('[data-testid="weekly-stat-line-loading"]')).toBeVisible()
  await expect(page.locator('[data-testid="weekly-stat-line-absent"]')).toHaveCount(0)

  // …and once it lands, the real panel replaces it — so the loading state is not a dead end.
  await expect(page.locator('[data-testid="weekly-stat-line"]')).toBeVisible({ timeout: 15_000 })
  await expect(page.locator('[data-testid="weekly-stat-line-loading"]')).toHaveCount(0)
  expectApiFullyMocked(mock)
})

test("a player with no component line gets a stated absence, not zeros and not the lock", async ({ page }) => {
  await signIn(page, { groups: ["subscriber"] })
  await openWeekly(page, { entitlement: "entitled" })

  // The fixture carries exactly one such row BY CONSTRUCTION — the component head is independent
  // and can legitimately have produced nothing for a player the points head projected.
  const noLine: Player = ENTITLED.players.find(
    (p: Player) => p.status === "projected" && p.passYds == null && p.recYds == null && p.rushYds == null,
  )
  expect(noLine, "no component-less row in the fixture — this clause would pass on nothing").toBeTruthy()

  await page.locator(`[data-testid="weekly-row"][data-player-id="${noLine.id}"]`)
    .locator('[data-testid="weekly-detail-toggle"]').click()

  if (WEEKLY_NUMBERS_WITHHELD) {
    // ⭐ EVEN ON THE ROW THAT GENUINELY HAS NOTHING, the withheld sentence is the right one: we are
    // declining to publish this fit's component line at all, so "the model had nothing to say about
    // him" would be answering a question we are not currently asking. Three states, and the one on
    // screen has to be the true one.
    await expect(page.locator('[data-testid="weekly-stat-line-withheld"]')).toBeVisible()
    await expect(page.locator('[data-testid="weekly-stat-line-absent"]')).toHaveCount(0)
  } else {
    await expect(page.locator('[data-testid="weekly-stat-line-absent"]')).toBeVisible()
  }
  await expect(page.locator('[data-testid="weekly-stat-line-locked"]')).toHaveCount(0)
  await expect(page.locator('[data-testid="weekly-stat-line"]')).toHaveCount(0)
})

// ══ 7 — the claims discipline, over the RENDERED page ═══════════════════════════════════════════

test("the rendered page makes no matchup claim and no forbidden market claim", async ({ page }) => {
  await openWeekly(page)
  await expect(page.locator('[data-testid="weekly-row"]').first()).toBeVisible()
  const body = await page.evaluate(() => document.body.innerText)

  // ⭐ THE MATCHUP PHRASES ARE THE CONTRACT'S OWN (`nfl_weekly.FORBIDDEN_CLAIM_PHRASES`), mirrored
  // here for the browser exactly as the claim denylist is. NF-W1 MEASURED the matchup foil losing
  // at every projected position — and losing to the flat foil too — so this is a claim our own
  // field contradicts, not a stylistic preference.
  const matchupPhrases = [
    "matchup-based", "matchup based", "matchup-driven", "matchup driven",
    "based on matchup", "beats the matchup",
  ]
  const matchupHits = matchupPhrases.filter((p) => body.toLowerCase().includes(p))
  expect(matchupHits, `the weekly page claims ${matchupHits.join(", ")}`).toEqual([])

  expect(forbiddenPhrasesIn(body), "the weekly page makes a forbidden claim").toEqual([])

  // No forecast promise: the point is an expectation over a distribution, and the page says so.
  for (const promise of ["will score", "guaranteed to", "is going to score"]) {
    expect(body.toLowerCase()).not.toContain(promise)
  }
})

test("the PPR framing says other formats do not exist yet — never that they are withheld", async ({ page }) => {
  await openWeekly(page)
  const panel = page.locator('[data-testid="weekly-ppr-native"]')
  await expect(panel).toBeVisible()
  const text = (await panel.innerText()).toLowerCase()

  // ⭐ THE LOAD-BEARING HALF. The season board has thirteen formats with one free; the weekly point
  // has ONE and it is not a paywall. Copy reading "one free format" would imply twelve locked ones
  // and would be selling something we cannot deliver at any price.
  expect(text).toContain("not being withheld")
  expect(text).not.toContain("one free format")
  expect(text).not.toContain("unlock")

  // …and nothing on the page offers a format picker over formats that do not exist.
  await expect(page.locator("select")).toHaveCount(0)
})

// ══ 8 — the served framing notes are rendered VERBATIM ══════════════════════════════════════════

test("the served interval notes are rendered verbatim, not paraphrased", async ({ page }) => {
  await openWeekly(page)
  const interval = await page.locator('[data-testid="weekly-interval-note"]').innerText()
  const ros = await page.locator('[data-testid="weekly-ros-interval-note"]').innerText()
  // Read from the FIXTURE — these are the payload's own prose, and a component that rewrote them
  // would be publishing claim copy that no screening had ever seen.
  expect(interval.trim()).toBe(MANIFEST.framing.interval_note)
  expect(ros.trim()).toBe(MANIFEST.framing.ros_interval_note)
})

// ══ 8a — THE FRAMING BLOCK, BOTH WAYS ═════════════════════════════════════════

/**
 * NF-INC-0917 — THE OUTAGE THIS PAIR EXISTS TO MAKE IMPOSSIBLE.
 *
 * On 2026-09-15 `/fantasy/weekly` answered every visitor with React's error page. The served
 * manifest carried NO `framing` block and the page dereferenced `framing.interval_note` unguarded.
 *
 * ⭐⭐ WHY THE WHOLE SUITE WAS GREEN THROUGH IT, which is the finding and not an excuse. Test 8
 * above already read both notes AND `openWeekly` already collected page errors — so the assertions
 * existed. What did not exist was a PAYLOAD that omits the block: every weekly spec runs against
 * `fantasy-nfl-weekly-manifest.synthetic.json`, which is generated by the SHIPPING writer and
 * therefore always carries `framing`. The suite could only ever exercise the branch that worked.
 * A guard is only as good as the states its fixtures can reach (NF1.7 (a)), and this is that class
 * on the FIXTURE rather than on the assertion.
 *
 * ⛔ THE ABSENT CASE IS BUILT BY DELETING THE KEY FROM THE REAL PAYLOAD, never by hand-writing a
 * second fixture. A fixture written to match the bug would drift from the shipping writer and stop
 * describing anything (NF-C0e: a fixture derived from the thing it tests cannot disconfirm it);
 * deleting one key from the real blob reproduces PRECISELY what production served.
 */

/** The real manifest with `framing` removed — byte-for-byte what the live payload looked like. */
const withoutFraming = (pathname: string, body: any) => {
  if (pathname !== "/fantasy/nfl/weekly/manifest") return body
  const { framing, ...rest } = body
  return rest
}

test("the framing block is REMOVABLE from the fixture — otherwise the absent case tests nothing", () => {
  // Non-vacuity, first and separately (NF1.7 (a)). If the fixture stopped carrying `framing`, the
  // PRESENT case below would assert on nothing AND the ABSENT case would be indistinguishable from
  // it — two clauses passing for the same wrong reason.
  expect(MANIFEST.framing, "the fixture has no `framing` — both clauses below are vacuous").toBeTruthy()
  expect(typeof MANIFEST.framing.interval_note).toBe("string")
  expect(typeof MANIFEST.framing.ros_interval_note).toBe("string")
  expect("framing" in withoutFraming("/fantasy/nfl/weekly/manifest", MANIFEST)).toBe(false)
  // ...and the transform must leave every OTHER read alone, or the absent case would be testing a
  // mangled page rather than a mangled manifest.
  expect(withoutFraming("/fantasy/nfl/weekly/projections", FREE)).toBe(FREE)
})

test("framing PRESENT: both served notes render, and nothing claims they are missing", async ({ page }) => {
  const { errors } = await openWeekly(page)
  await expect(page.locator('[data-testid="weekly-interval-note"]')).toBeVisible()
  await expect(page.locator('[data-testid="weekly-ros-interval-note"]')).toBeVisible()
  // ⭐ THE HALF THAT KEEPS THE ABSENT CLAUSE HONEST. Without it, a page that rendered the absence
  // copy unconditionally — beside the notes — would satisfy both clauses at once.
  await expect(page.locator('[data-testid="weekly-framing-absent"]')).toHaveCount(0)
  expectNoPageErrors(errors)
})

test("framing ABSENT: the page renders and STATES the absence — it does not crash", async ({ page }) => {
  const { errors } = await openWeekly(page, { transform: withoutFraming })

  // 1. IT DOES NOT CRASH. The literal regression: this was an uncaught TypeError that took the
  //    whole route down, so the page-error channel is the primary assertion, not a formality.
  expectNoPageErrors(errors)

  // 2. THE FRAME SURVIVES. "Suppress the note, keep the page" — an error page is neither honest nor
  //    up. The table, its rows and the week label are all unaffected by a missing caveat block.
  await expect(page.locator('[data-testid="weekly-week-label"]')).toBeVisible()
  await expect(page.locator('[data-testid="weekly-row"]').first()).toBeVisible()
  await expect(page.locator('[data-testid="weekly-provenance"]')).toBeVisible()

  // 3. THE ABSENCE IS STATED, and the vanished notes are really gone — a clause that only checked
  //    for the new copy would pass on a page that rendered BOTH.
  await expect(page.locator('[data-testid="weekly-interval-note"]')).toHaveCount(0)
  await expect(page.locator('[data-testid="weekly-ros-interval-note"]')).toHaveCount(0)
  const absent = page.locator('[data-testid="weekly-framing-absent"]')
  await expect(absent).toBeVisible()

  // 4. IT IS A STATED ABSENCE, NOT A PARAPHRASE. The page must not invent a coverage claim to
  //    stand in for the measurement it did not receive.
  const text = await absent.innerText()
  expect(text.trim().length).toBeGreaterThan(40)
  expect(forbiddenPhrasesIn(text), `the absence copy makes a denied claim: ${text}`).toEqual([])

  // 5. AND NOTHING ELSE SILENTLY WENT MISSING WITH IT.
  await expectNoNaN(page)
})

// ══ 8b — provenance: every vintage on one line, in one format ═══════════════════════════════════

test("the provenance line renders every input vintage in one readable format", async ({ page }) => {
  await openWeekly(page)
  const line = await page.locator('[data-testid="weekly-provenance"]').innerText()

  // ⭐ THE LINE EXISTS SO STALENESS IS LEGIBLE AT A GLANCE (NF-FRESH2). A raw ISO timestamp beside
  // a locale-formatted build time is visible but not legible, and makes the line read as two
  // different kinds of fact — so no raw ISO may survive into the rendered text.
  const rawIso = line.match(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/g) ?? []
  expect(rawIso, `the provenance line still carries raw ISO timestamps: ${rawIso.join(", ")}`).toEqual([])

  // …and it still NAMES each input, rather than collapsing them into one build date — which is the
  // defect NF-FRESH2 exists to prevent and which "no raw ISO" would also be satisfied by.
  for (const label of ["rosters", "schedule", "stats", "trained through"]) {
    expect(line.toLowerCase()).toContain(label)
  }
  expect(line).toContain(MANIFEST.lineage.served_version)
})

// ══ 9 — the nav door ════════════════════════════════════════════════════════════════════════════

/**
 * ⭐ ASSERTED ON REACHABILITY, NOT ON A MARKER — and the choice is deliberate.
 *
 * The signed-in dropdown items carry no `data-nav-active` attribute at all (only `SIGNED_OUT_NAV`
 * entries and the top-level NCAAF link do); they express the active state through a class. Adding
 * an attribute to the shared renderer to make this clause easier would have touched every season
 * item, which this story may not do — and asserting the class would be testing that somebody typed
 * a string, which is the NF-C4 defect this whole file avoids.
 *
 * What actually matters is the NCAAF-P3.9 failure: a live surface with no route to it. So the
 * clause drives the menu the way a reader does — hover, see the item, click it, land on the page.
 */
test("the weekly page is reachable from the NFL fantasy menu, beside the season board", async ({ page }) => {
  await signIn(page, { groups: ["subscriber"] })
  await mockApi(page, { entitlement: "entitled" })
  await page.goto("/about")
  await page.waitForLoadState("networkidle")

  const nflTrigger = page.locator("[data-primary-nav] button").filter({ hasText: /^NFL/ }).first()
  await expect(nflTrigger, "the signed-in sub-nav did not render — the seeded session did not take")
    .toBeVisible()
  await nflTrigger.hover()
  const menu = nflTrigger.locator("xpath=..").locator("div.absolute")

  const item = menu.getByRole("link", { name: "This Week" })
  await expect(item, "the weekly page has no door in the NFL menu").toBeVisible()

  // ⭐ BESIDE THE SEASON BOARD, asserted as ADJACENCY rather than as an index, so adding an item
  // elsewhere in the menu cannot fail this for the wrong reason. The two answer the same question
  // over different horizons, which is exactly why they belong next to each other.
  const links = await menu.getByRole("link").evaluateAll((els) =>
    els.map((e) => (e.textContent ?? "").trim()),
  )
  const weekly = links.indexOf("This Week")
  const projections = links.indexOf("Projections")
  expect(projections, "Projections is missing from the NFL menu").toBeGreaterThanOrEqual(0)
  expect(weekly, "This Week is missing from the NFL menu").toBeGreaterThanOrEqual(0)
  expect(
    Math.abs(weekly - projections),
    `This Week is not beside Projections in the NFL menu: ${links.join(" | ")}`,
  ).toBe(1)

  // …and it actually GOES there. A menu entry that does not navigate is the NCAAF-P3.9 defect
  // wearing a link's clothes.
  await item.click()
  await page.waitForURL(`**${WEEKLY_URL}`)
  await expect(page.locator('[data-testid="weekly-ppr-native"]')).toBeVisible()
})
