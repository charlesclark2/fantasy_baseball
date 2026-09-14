import { expect, test, type Page } from "@playwright/test"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { collectPageErrors, mockApi, type MockOptions } from "../support/api-mock"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"
import { signIn } from "../support/signed-in"

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
  expect(withBand, `${total - withBand} of ${total} rows render a point with no band`).toBe(total)

  expectApiFullyMocked(mock)
  await expectNoNaN(page)
  expectNoPageErrors(errors)
})

test("the band shown is the payload's own p10–p90, not a recomputed one", async ({ page }) => {
  await openWeekly(page)
  const row = page.locator(`[data-testid="weekly-row"][data-player-id="${projectedRow.id}"]`)
  await expect(row).toBeVisible()
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

  await expect(row.locator('[data-testid="weekly-bye-chip"]')).toBeVisible()

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
  await expect(page.locator('[data-testid="weekly-stat-line-locked"]')).toBeVisible()
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
  await expect(page.locator('[data-testid="weekly-stat-line-absent"]')).toBeVisible()
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
