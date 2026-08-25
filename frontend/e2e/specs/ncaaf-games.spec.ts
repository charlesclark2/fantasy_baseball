import { expect, test, type Page } from "@playwright/test"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { collectPageErrors, mockApi, type MockOptions } from "../support/api-mock"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors, internalHrefs } from "../support/assertions"
import { forbiddenPhrasesIn } from "../support/claim-denylist"

/**
 * NCAAF-P3.2 — THE FLAGSHIP COLLEGE-FOOTBALL SURFACE, AT THE RENDER LEVEL.
 *
 * ⭐ WHY EVERY ASSERTION HERE IS ON RENDERED OUTPUT. NF-C4 measured eight frontend defects that
 * were all green in CI because the suite asserted on SOURCE — a guard that greps a component, or
 * walks a className, tests that somebody TYPED a string. Nothing below reads this repo's source:
 * each clause reads the DOM the browser produced, and every number it checks is read from the
 * FIXTURE'S OWN VALUES rather than typed here, so a re-capture moves the expectation with the
 * payload instead of turning the suite red for the wrong reason.
 *
 * WHAT THIS SURFACE IS, AND THE THREE THINGS THAT COULD GO WRONG SILENTLY:
 *
 *   1. THE CURVE COULD BE A PICTURE OF NOTHING. A `<path>` renders whether or not its `d` came
 *      from the served quantiles, and an empty or degenerate path looks like a quiet card rather
 *      than like a bug. So the curve clauses read the drawn geometry: the path's own point count,
 *      the shaded band's position, and — the load-bearing one — that the band's BOUNDS are the
 *      payload's `interval_lo`/`interval_hi` verbatim rather than something recomputed from μ/σ.
 *
 *   2. AN ABSENT MARKET LINE COULD RENDER AS PARITY. Every game on the live wire is
 *      `market.status = "unavailable"` (P3.1 closeout item 2), so this is the branch nearly every
 *      reader meets. A blank cell in a two-column comparison reads as agreement and a zero reads as
 *      a line of zero; both are a fabricated market view.
 *
 *   3. THE COPY COULD DRIFT INTO A CLAIM. `best_alpha = 0` — VAL1 came back ALL_BUCKETS_NULL, ATS
 *      0.496 against the close, indistinguishable from a placebo. The denylist runs over the WHOLE
 *      RENDERED PAGE, not over the copy module, because a component's inline heading is exactly
 *      where a stronger sentence would appear and no module-level screen can see it.
 */

const FIXTURE_DIR = join(process.cwd(), "e2e", "fixtures", "api")
const readFixture = (name: string) => JSON.parse(readFileSync(join(FIXTURE_DIR, name), "utf8"))

const MANIFEST = readFixture("ncaaf-manifest.json")
const SLATE = readFixture("ncaaf-slate-2026-08-29.json")
const SLATE_MARKET = readFixture("ncaaf-slate-2026-08-29-market.synthetic.json")
const SLATE_DEGRADED = readFixture("ncaaf-slate-degraded.synthetic.json")

const PATH = "/ncaaf/games"

async function open(page: Page, options: MockOptions = {}) {
  const errors = collectPageErrors(page)
  const mock = await mockApi(page, options)
  await page.goto(PATH)
  return { mock, errors }
}

const card = (page: Page, gameId: number | string) =>
  page.locator(`[data-testid="ncaaf-game-card"][data-game-id="${gameId}"]`)

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 1. The happy path — the real captured slate
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("the captured slate renders one card per game, in kickoff order", async ({ page }) => {
  const { mock, errors } = await open(page)
  const cards = page.getByTestId("ncaaf-game-card")
  await expect(cards).toHaveCount(SLATE.games.length)

  // ⭐ ORDER IS THE ASSERTION, not merely the count. Cards are ordered by KICKOFF TIME and by
  // nothing else — ranking a board by any function of the numbers would be a pick expressed as an
  // ordering, which `best_alpha = 0` forbids. Comparing against the fixture's own time-sorted ids
  // is what makes "we did not sort by anything else" a testable statement.
  const expected = [...SLATE.games]
    .sort((a: any, b: any) => Date.parse(a.commence_time) - Date.parse(b.commence_time))
    .map((g: any) => String(g.game_id))
  const rendered = await cards.evaluateAll((els) =>
    els.map((e) => e.getAttribute("data-game-id") ?? ""),
  )
  expect(rendered).toEqual(expected)

  await expectNoNaN(page)
  expectNoPageErrors(errors)
  expectApiFullyMocked(mock)
})

test("the win probability leads the card and both sides come from the payload", async ({ page }) => {
  await open(page)
  // Every game, not a sample: a component that rendered the home side into both slots would pass a
  // one-card check on any game whose two numbers happen to be close.
  for (const g of SLATE.games) {
    const c = card(page, g.game_id)
    const home = `${Math.round(g.win_probability.home * 100)}%`
    const away = `${Math.round(g.win_probability.away * 100)}%`
    await expect(c.getByTestId("ncaaf-win-probability-home")).toHaveText(home)
    await expect(c.getByTestId("ncaaf-win-probability-away")).toHaveText(away)
  }
})

test("the win probability is the largest text on the card", async ({ page }) => {
  // The P3 brand directive's first clause is "LEAD with the win probability". A card that rendered
  // it in the same size as the provenance list would satisfy every text assertion above while
  // failing the directive, and only computed layout can tell the two apart.
  await open(page)
  const c = card(page, SLATE.games[0].game_id)
  const probSize = await c
    .getByTestId("ncaaf-win-probability-home")
    .evaluate((el) => parseFloat(getComputedStyle(el).fontSize))
  const headingSize = await c
    .locator("h3")
    .evaluate((el) => parseFloat(getComputedStyle(el).fontSize))
  expect(probSize).toBeGreaterThan(headingSize)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 2. The signature viz
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("both curves are drawn from the served quantiles, not from the parameters", async ({ page }) => {
  await open(page)
  const c = card(page, SLATE.games[0].game_id)
  for (const which of ["margin", "total"]) {
    const curve = c.getByTestId(`ncaaf-curve-${which}`)
    // `quantiles` — the served ladder — rather than `parametric`. The captured payload carries a
    // full ladder, so a build that silently fell back to drawing a normal from μ/σ would be
    // invisible in the picture and is caught here.
    await expect(curve).toHaveAttribute("data-curve-source", "quantiles")
    const d = await c.getByTestId(`ncaaf-curve-${which}-path`).getAttribute("d")
    // A `<path>` with an empty or one-point `d` renders as nothing and looks like a quiet card.
    expect((d ?? "").split(/[ML]/).length).toBeGreaterThan(20)
  }
})

test("the shaded band is the SERVED interval, and its label names the served levels", async ({ page }) => {
  // ⭐ THE LOAD-BEARING CURVE CLAUSE. `mu ± 1.2816σ` would be a second, drifting copy of a number
  // the payload already carries (E9.61) and would silently disagree with the server the moment the
  // predictive stopped being Gaussian. Reading the rendered bounds back and comparing them to the
  // payload is what makes "the band is served, never recomputed" a fact rather than a comment.
  await open(page)
  const g = SLATE.games[0]
  const c = card(page, g.game_id)
  for (const [which, dist] of [["margin", g.margin], ["total", g.total]] as const) {
    const text = await c.getByTestId(`ncaaf-curve-${which}-band`).innerText()
    expect(text).toContain(dist.interval_lo.toFixed(1))
    expect(text).toContain(dist.interval_hi.toFixed(1))
    // The band's NAME is computed from the served levels (0.10/0.90 → "80%"), never from a literal.
    const pct = Math.round((dist.interval_hi_level - dist.interval_lo_level) * 100)
    expect(text).toContain(`${pct}%`)
    await expect(c.getByTestId(`ncaaf-curve-${which}-band-shade`)).toBeVisible()
  }
})

test("a margin curve carries the even-money reference and a total curve does not", async ({ page }) => {
  // Zero is meaningful on a margin (the win/loss boundary) and meaningless on a total. A component
  // that drew the reference on both would put a line labelled "even" at a total of zero points.
  await open(page)
  const c = card(page, SLATE.games[0].game_id)
  await expect(c.getByTestId("ncaaf-curve-margin-zero")).toBeAttached()
  await expect(c.getByTestId("ncaaf-curve-total-zero")).toHaveCount(0)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 3. Model and market — both branches
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("with no captured line the market column says so, and never blanks or zeroes", async ({ page }) => {
  await open(page)
  const g = SLATE.games[0]
  expect(g.market.status).toBe("unavailable") // the capture's own state; see the file header
  const panel = card(page, g.game_id).getByTestId("ncaaf-market-comparison")
  await expect(panel).toHaveAttribute("data-market-status", "unavailable")
  for (const row of ["margin", "total", "winprob"]) {
    const cell = panel.getByTestId(`ncaaf-market-comparison-${row}-market`)
    await expect(cell).toHaveText("No market line")
  }
  // The machine-readable reason, said in words. The contract carries it precisely so a surface can
  // distinguish the causes of a null line; collapsing them at the last hop would throw that away.
  await expect(panel.getByTestId("ncaaf-market-comparison-absent-reason")).toContainText(
    "have not captured a closing line",
  )
})

test("a captured line renders in the model's units, and no difference is ever shown", async ({ page }) => {
  await open(page, { ncaafSlate: "market" })
  const priced = SLATE_MARKET.games.filter((g: any) => g.market.status === "available")
  expect(priced.length).toBeGreaterThan(0)
  for (const g of priced) {
    const panel = card(page, g.game_id).getByTestId("ncaaf-market-comparison")
    await expect(panel).toHaveAttribute("data-market-status", "available")
    // The book quotes a home SPREAD (negative = home favoured); the model publishes a home MARGIN.
    // Same quantity, opposite sign convention — so the panel negates it to put both numbers under
    // one heading. A build that forgot the negation would show the market backing the WRONG TEAM,
    // which is the most consequential silent error available on this panel.
    const implied = -g.market.home_spread
    const shown = `${implied > 0 ? "+" : ""}${implied.toFixed(1)}`
    await expect(panel.getByTestId("ncaaf-market-comparison-margin-market")).toHaveText(shown)
    await expect(panel.getByTestId("ncaaf-market-comparison-total-market")).toHaveText(
      g.market.total.toFixed(1),
    )
  }

  // ⛔ NO DIFFERENCE COLUMN, EVER. The served contract declares none on purpose: "model beats
  // market by 3.5" is the claim VAL1's null forbids, and a signed difference column is one rename
  // away from being read as exactly that. Three columns and no more.
  const columns = await card(page, priced[0].game_id)
    .getByTestId("ncaaf-market-comparison-margin")
    .evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(" ").length)
  expect(columns).toBe(3)
})

test("the mixed slate prices some games and not others", async ({ page }) => {
  // A fixture where every game had a line could not tell "the panel renders a line" from "the panel
  // renders whatever it is handed" — and a mixed slate is also the state a real in-season Saturday
  // will be in.
  await open(page, { ncaafSlate: "market" })
  const statuses = await page
    .getByTestId("ncaaf-market-comparison")
    .evaluateAll((els) => els.map((e) => e.getAttribute("data-market-status")))
  expect(new Set(statuses)).toEqual(new Set(["available", "unavailable"]))
})

test("a market read that FAILED reads differently from one that was never captured", async ({ page }) => {
  // Two causes, two sentences (NF-C6b). The degraded fixture carries `market_read_failed` on one
  // game and `no_line_captured_for_this_kickoff` on the others.
  await open(page, { ncaafSlate: "degraded" })
  const failed = SLATE_DEGRADED.games.find((g: any) => g.market.reason === "market_read_failed")
  const notYet = SLATE_DEGRADED.games.find(
    (g: any) => g.market.reason === "no_line_captured_for_this_kickoff",
  )
  expect(failed && notYet).toBeTruthy()
  const a = await card(page, failed.game_id)
    .getByTestId("ncaaf-market-comparison-absent-reason")
    .innerText()
  const b = await card(page, notYet.game_id)
    .getByTestId("ncaaf-market-comparison-absent-reason")
    .innerText()
  expect(a).not.toEqual(b)
  expect(a).toContain("could not read")
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 4. Degraded games — the optional-field floor
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("a game with no distribution says so instead of drawing a flat line", async ({ page }) => {
  await open(page, { ncaafSlate: "degraded" })
  const g = SLATE_DEGRADED.games.find((x: any) => x.margin.mu === null && x.margin.quantiles.length === 0)
  const c = card(page, g.game_id)
  await expect(c.getByTestId("ncaaf-curve-margin")).toHaveAttribute("data-curve-source", "unavailable")
  await expect(c.getByTestId("ncaaf-curve-margin")).toContainText("No distribution published")
  await expect(c.getByTestId("ncaaf-curve-margin-path")).toHaveCount(0)
  // The card still renders the parts it HAS: a game with one gap must not vanish.
  await expect(c.getByTestId("ncaaf-win-probability-home")).toBeVisible()
})

test("a game with parameters but no quantile ladder draws the fallback AND labels it", async ({ page }) => {
  // ⭐ A bell drawn from two parameters and a curve drawn from the model's own simulated quantiles
  // are different pictures. Drawing the fallback silently would present one as the other.
  await open(page, { ncaafSlate: "degraded" })
  const g = SLATE_DEGRADED.games.find(
    (x: any) => x.margin.mu !== null && x.margin.quantiles.length === 0,
  )
  const c = card(page, g.game_id)
  await expect(c.getByTestId("ncaaf-curve-margin")).toHaveAttribute("data-curve-source", "parametric")
  await expect(c.getByTestId("ncaaf-curve-margin-parametric-note")).toBeVisible()
  // No served interval on that game, so nothing is shaded — ⛔ and nothing is invented from μ/σ.
  await expect(c.getByTestId("ncaaf-curve-margin-band")).toHaveCount(0)
  await expect(c.getByTestId("ncaaf-curve-margin-band-shade")).toHaveCount(0)
})

test("a game with no win probability says so and still draws its curves", async ({ page }) => {
  await open(page, { ncaafSlate: "degraded" })
  const g = SLATE_DEGRADED.games.find((x: any) => x.win_probability.home === null)
  const c = card(page, g.game_id)
  await expect(c.getByTestId("ncaaf-win-probability")).toHaveAttribute("data-win-probability", "absent")
  await expect(c.getByTestId("ncaaf-win-probability")).toContainText("No win probability")
  await expect(c.getByTestId("ncaaf-curve-margin")).toHaveAttribute("data-curve-source", "quantiles")
})

test("a game with no team names or kickoff time renders stated placeholders", async ({ page }) => {
  await open(page, { ncaafSlate: "degraded" })
  const g = SLATE_DEGRADED.games.find((x: any) => x.home.team === null)
  const c = card(page, g.game_id)
  // "TBD" is a fact about the payload; an empty span is a fact about our rendering.
  await expect(c.locator("h3")).toContainText("Team TBD")
  await expect(c.getByTestId("ncaaf-kickoff")).toHaveText("Kickoff time TBD")
})

test("the degraded slate renders without NaN or an uncaught error", async ({ page }) => {
  const { errors } = await open(page, { ncaafSlate: "degraded" })
  await expect(page.getByTestId("ncaaf-game-card")).toHaveCount(SLATE_DEGRADED.games.length)
  await expectNoNaN(page)
  expectNoPageErrors(errors)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 5. The day selector and the empty states — four different facts
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("the surface opens on a published day even when 'today' has none", async ({ page }) => {
  // ⭐ THE MEASURED CASE. The captured manifest's `current_game_day` is NOT in `game_days` — before
  // the opener "today" is a weekday. Opening on `current_game_day` would 404 and make a working
  // surface look broken on most days of the week.
  expect(MANIFEST.game_days.map((d: any) => d.game_day)).not.toContain(MANIFEST.current_game_day)
  const { mock } = await open(page)
  await expect(page.getByTestId("ncaaf-game-list")).toBeVisible()
  const asked = mock.requested.filter((r) => r.startsWith("/ncaaf/games"))
  expect(asked.some((r) => r.includes(MANIFEST.game_days[0].game_day))).toBe(true)
  await expect(
    page.locator('[data-testid="ncaaf-day-option"][data-active="true"]'),
  ).toHaveAttribute("data-game-day", MANIFEST.game_days[0].game_day)
})

test("the day picker offers every published day with its game count", async ({ page }) => {
  await open(page)
  const options = page.getByTestId("ncaaf-day-option")
  await expect(options).toHaveCount(MANIFEST.game_days.length)
  for (const d of MANIFEST.game_days) {
    await expect(
      page.locator(`[data-testid="ncaaf-day-option"][data-game-day="${d.game_day}"]`),
    ).toContainText(`${d.n_games} game`)
  }
})

test("choosing a day with nothing published says so, and it is not the failure message", async ({ page }) => {
  // A 404 is the ORDINARY state of a Tuesday, not a fault. Rendering it as an error would train a
  // reader to ignore the real one.
  await open(page, { ncaafSlate: "empty" })
  await expect(page.getByTestId("ncaaf-empty-day")).toBeVisible()
  await expect(page.getByTestId("ncaaf-slate-error")).toHaveCount(0)
  await expect(page.getByTestId("ncaaf-game-card")).toHaveCount(0)
})

test("a failed read says the fault is ours, and it is not the empty message", async ({ page }) => {
  await open(page, { ncaafSlate: "failed" })
  await expect(page.getByTestId("ncaaf-slate-error")).toBeVisible()
  await expect(page.getByTestId("ncaaf-empty-day")).toHaveCount(0)
})

test("a season with nothing published reads differently from an empty day", async ({ page }) => {
  await open(page, { ncaafManifest: "none" })
  await expect(page.getByTestId("ncaaf-nothing-published")).toBeVisible()
  await expect(page.getByTestId("ncaaf-day-picker")).toHaveCount(0)
  await expect(page.getByTestId("ncaaf-empty-day")).toHaveCount(0)
})

test("a failed manifest read does not present as an empty season", async ({ page }) => {
  await open(page, { ncaafManifest: "failed" })
  await expect(page.getByTestId("ncaaf-manifest-error")).toBeVisible()
  await expect(page.getByTestId("ncaaf-nothing-published")).toHaveCount(0)
})

// ══════════════════════════════════════════════════════════════════════════════════════════════
// 6. Honest framing — the highest-risk half
// ══════════════════════════════════════════════════════════════════════════════════════════════

test("the SERVED disclosure is rendered verbatim", async ({ page }) => {
  // ⭐ NOT A LOCAL COPY. `app/backend/models/ncaaf.py::DISCLOSURE` is pinned verbatim by a backend
  // guard so a reword is a reviewed change; a second copy in the frontend would be free to drift,
  // and the drifting copy is the one the reader would actually see.
  await open(page)
  await expect(page.getByTestId("ncaaf-disclosure")).toHaveText(SLATE.framing.disclosure)
})

test("every rendered word passes the claim denylist", async ({ page, browserName }) => {
  // Over the WHOLE RENDERED PAGE rather than over the copy module, because a component's inline
  // heading is exactly where a stronger sentence would appear and no module-level screen can see
  // it. Run in all three data modes so a claim hiding in a degraded branch is caught too.
  for (const mode of ["captured", "market", "degraded"] as const) {
    const context = await page.context().browser()!.newContext()
    const p = await context.newPage()
    await mockApi(p, { ncaafSlate: mode })
    await p.goto(PATH)
    await expect(p.getByTestId("ncaaf-disclosure")).toBeVisible()
    const text = await p.evaluate(() => document.body.innerText)
    expect(forbiddenPhrasesIn(text), `mode=${mode} browser=${browserName}`).toEqual([])
    await context.close()
  }
})

test("a payload whose framing flags change makes the surface WITHDRAW its own copy", async ({ page }) => {
  // ⭐ THE FLAGS BEING RESPECTED RATHER THAN MERELY PRESENT. Every claim-bearing sentence on this
  // surface is warranted by `market_blind && projection_only && best_alpha === 0` and by nothing
  // else — so on a payload that stops carrying them, continuing to assert "we make no claim to an
  // advantage over the market" would be describing a model this page was not written to describe.
  //
  // ⚠️ IT CANNOT FIRE TODAY — the write path refuses a non-zero `best_alpha` outright. That is the
  // point: the guarantee lives in a writer this client cannot see, across a deploy boundary it
  // cannot control (the API Lambda has no CD — NF-C0), so the client asserts it for itself.
  await open(page, {
    transform: (pathname, body) =>
      pathname.startsWith("/ncaaf/games")
        ? {
            ...body,
            games: body.games.map((g: any) => ({
              ...g,
              framing: { ...g.framing, market_blind: false, best_alpha: 0.02 },
            })),
          }
        : body,
  })
  const panel = card(page, SLATE.games[0].game_id).getByTestId("ncaaf-market-comparison")
  await expect(panel).toHaveAttribute("data-posture", "changed")
  await expect(panel.getByTestId("ncaaf-market-comparison-framing")).toHaveCount(0)
  const withdrawn = panel.getByTestId("ncaaf-market-comparison-framing-withdrawn")
  await expect(withdrawn).toBeVisible()
  // The publisher's OWN disclosure is what stands in — a refusal, never a re-interpretation.
  await expect(withdrawn).toContainText(SLATE.framing.disclosure.slice(0, 60))
  // ⛔ And the surface still claims nothing itself.
  expect(forbiddenPhrasesIn(await page.evaluate(() => document.body.innerText))).toEqual([])
})

test("the market panel states the no-advantage framing on every card", async ({ page }) => {
  await open(page, { ncaafSlate: "market" })
  const framings = page.getByTestId("ncaaf-market-comparison-framing")
  await expect(framings).toHaveCount(SLATE_MARKET.games.length)
  await expect(framings.first()).toContainText("make no claim to an advantage")
  // The two-sided half of the clause above: on the REAL payload the posture holds, so a component
  // that withdrew its copy unconditionally would pass that test and say nothing on any real card.
  await expect(page.getByTestId("ncaaf-market-comparison").first()).toHaveAttribute(
    "data-posture",
    "market_blind_projection",
  )
})

test("no link on the surface points at a route that does not exist", async ({ page }) => {
  // P3.3's team page is not built. The stub is an affordance, not an anchor — a CTA pointing at a
  // 404 is precisely the defect this suite exists to catch (E9.56c).
  await open(page)
  const stub = page.getByTestId("ncaaf-team-page-stub").first()
  await expect(stub).toBeVisible()
  await expect(stub).toBeDisabled()
  const hrefs = await internalHrefs(page)
  expect(hrefs.filter((h) => h.startsWith("/ncaaf/teams"))).toEqual([])
})

test("a game whose kickoff has passed says so, and does not read as upcoming", async ({ page }) => {
  // ⭐ THE OPENING-DAY CASE, and it is invisible to every other clause here because they all run on
  // a day when the captured slate is still in the future.
  //
  // The served payload is a PRE-KICKOFF snapshot with no game state and no score, so on the evening
  // of a slate the cards would otherwise show projections for games that are underway or finished,
  // rendered identically to games that have not started. `page.clock` is what lets that day be
  // tested on any other day.
  const kickoff = Date.parse(SLATE.games[0].commence_time)
  await page.clock.install({ time: new Date(kickoff + 45 * 60_000) }) // 45 minutes in
  const { errors } = await open(page)
  const c = card(page, SLATE.games[0].game_id)
  await expect(c.getByTestId("ncaaf-kicked-off")).toBeVisible()
  await expect(c.getByTestId("ncaaf-kicked-off-note")).toContainText("not updated once a game starts")

  // ⛔ AND IT MUST NOT CLAIM MORE THAN THE PAYLOAD SUPPORTS. There is no score and no state on the
  // wire, so nothing may read as a result or as a live game.
  //
  // ⭐ ASSERTED POSITIVELY — the chip says EXACTLY this and the note says EXACTLY that — rather
  // than by scanning the card for words like "live". The first cut did scan, and it FAILED on the
  // surface's own honest sentence ("we do not show live scores here"): a substring scan is
  // NEGATION-BLIND, so the cheapest way to satisfy it was to delete the disclaimer that makes the
  // card honest. That is the NF-DS finding reproduced inside the guard written to honour it, and
  // the cure is the one that lesson names — assert what IS rendered, not the absence of a token.
  await expect(c.getByTestId("ncaaf-kicked-off")).toHaveText("Kicked off")
  // No score anywhere on the card: the payload carries none, so a "24–17" could only be invented.
  expect(await c.innerText()).not.toMatch(/\b\d{1,3}\s*[-–—]\s*\d{1,3}\b/)
  // Words that have no honest use on a card with no game state. ⚠️ "live" is deliberately NOT in
  // this list — see above.
  const header = (await c.locator("header").innerText()).toLowerCase()
  for (const overreach of ["final", "won", "lost", "in progress", "halftime"]) {
    expect(header, `the card header claims "${overreach}" with no state on the wire`).not.toContain(
      overreach,
    )
  }
  // A LATER game on the same slate has NOT kicked off — a component that flagged every card would
  // pass the assertion above and be just as wrong.
  const later = SLATE.games[SLATE.games.length - 1]
  expect(Date.parse(later.commence_time)).toBeGreaterThan(kickoff + 45 * 60_000)
  await expect(card(page, later.game_id).getByTestId("ncaaf-kicked-off")).toHaveCount(0)
  expectNoPageErrors(errors)
})

test("before kickoff no card is flagged as started", async ({ page }) => {
  // The two-sided half. Without it, "flag a started game" is satisfied by a component that flags
  // everything, which is the failure that would land on every card the day the surface ships.
  await page.clock.install({ time: new Date(Date.parse(SLATE.games[0].commence_time) - 3600_000) })
  await open(page)
  await expect(page.getByTestId("ncaaf-kicked-off")).toHaveCount(0)
  await expect(page.getByTestId("ncaaf-kicked-off-note")).toHaveCount(0)
})

test("the pace note explains an inactive term rather than leaving it silent", async ({ page }) => {
  // `pace_term_active: false` at week 1 is CORRECT by construction (week-1 team-weeks carry no pace
  // input), and an unexplained false in a provenance list reads as a broken model.
  expect(SLATE.games[0].provenance.pace_term_active).toBe(false)
  await open(page)
  const c = card(page, SLATE.games[0].game_id)
  await c.getByTestId("ncaaf-provenance").locator("summary").click()
  await expect(c.getByTestId("ncaaf-pace-note")).toBeVisible()
})
