import { expect, test, type Page } from "@playwright/test"
import { FIXTURES, collectPageErrors, mockApi } from "../support/api-mock"
import { signIn } from "../support/session"
import { forbiddenPhrasesIn } from "../support/claim-denylist"
import { expectNoNaN, expectNoPageErrors } from "../support/assertions"
import { openEligibility, type LeagueConfigMeta, type Player } from "@/lib/draft-optimizer"
import {
  GRADE_CIRCULARITY_NOTE,
  boardOrder,
  marketOrder,
  simulateCpuPicks,
  type Pick,
} from "@/lib/mock-draft"

/**
 * NF-C2.1 — THE MOCK DRAFT SIMULATOR.
 *
 * Two halves, deliberately, because they can only be answered by different instruments:
 *
 *   1. **The CPU engine**, asserted directly on `lib/mock-draft` with no browser. "The opponents
 *      pick plausibly" is a claim about a distribution over ~100 picks; a rendered page can tell
 *      you a pick HAPPENED, it cannot tell you the room drafted like a draft room. These run in
 *      milliseconds and are the only place the plausibility claim is actually decided.
 *   2. **The loop**, driven in the browser: a mock runs start to finish, our recommendations render
 *      with their reasoning, and the roster grades — with the grade's circularity caveat on screen.
 *
 * ⭐ WHY THE FIXTURE MAKES THE PLAUSIBILITY ASSERTIONS DISCRIMINATING RATHER THAN VACUOUS. In
 * `fantasy-nfl-board-full_ppr-12-2026-free.json` the ADP column is REAL (carried verbatim from the
 * prod capture) while every model value — `pts`, `vor`, `ovrRank` — is SYNTHETIC, seeded off the
 * player id (see `build-entitled-fixture.mjs`). Measured on the committed fixture, the two orders
 * are essentially INDEPENDENT: Spearman ρ = 0.059 over the 226 ADP'd rows.
 *
 * That is a gift. It means "the CPU drafts off ADP" and "the CPU drafts off our board" are
 * SEPARATELY FALSIFIABLE here — an implementation that quietly ignored one source would still
 * satisfy the other, and the enrichment tests below would catch it. On a fixture where the two
 * orders agreed, both assertions would pass on either implementation and prove nothing.
 */

const CONFIG_NAME = "full_ppr"

function board(): Player[] {
  return FIXTURES.boardFree() as Player[]
}

function config(): LeagueConfigMeta {
  const m = FIXTURES.manifestFree() as { configs: LeagueConfigMeta[] }
  const c = m.configs.find((x) => x.name === CONFIG_NAME)
  if (!c) throw new Error(`the fixture manifest no longer carries the ${CONFIG_NAME} preset`)
  return c
}

/** A whole room drafted by CPUs. `mySlot: 0` is never on the clock (`slotOnClock` returns 1..n), so
 *  the sim fills every seat — which is exactly what an engine-level assertion wants. */
function fullRoom(seed: number, nTeams = 12, rounds = 10) {
  const b = board()
  const c = config()
  return simulateCpuPicks({
    board: b,
    config: c,
    picks: [],
    nTeams,
    mySlot: 0,
    seed,
    maxPicks: rounds * nTeams,
    market: marketOrder(b),
    boardRank: boardOrder(b),
  })
}

test.describe("the CPU opponents", () => {
  test("a fast-forward and a pick-at-a-time run produce the IDENTICAL draft", async () => {
    // ⭐ THE INVARIANT THE WHOLE UI RESTS ON. The screen reveals CPU picks on a timer, and "Skip to
    // my pick" resolves the rest in one synchronous loop. If those two paths could diverge, the
    // button would silently be a DIFFERENT draft — and a mid-draft reload (which replays from
    // stored picks) would be a third one. It holds only because the RNG is re-derived per pick from
    // (seed, overallPick, slot) rather than carried across the batch; delete that and this goes red.
    const b = board()
    const c = config()
    const common = {
      board: b,
      config: c,
      nTeams: 12,
      mySlot: 0,
      seed: 4242,
      maxPicks: 96,
      market: marketOrder(b),
      boardRank: boardOrder(b),
    }

    const allAtOnce = simulateCpuPicks({ ...common, picks: [] }).picks

    const oneAtATime: Pick[] = []
    for (let i = 0; i < 96; i++) {
      const step = simulateCpuPicks({ ...common, picks: oneAtATime, limit: 1 }).picks
      if (!step.length) break
      oneAtATime.push(...step)
    }

    expect(allAtOnce.length, "the sim did not fill the room").toBe(96)
    expect(
      oneAtATime.map((p) => `${p.slot}:${p.id}`),
      "skipping ahead produced a different draft from letting the clock run — the sim is not replayable",
    ).toEqual(allAtOnce.map((p) => `${p.slot}:${p.id}`))
  })

  test("the room drafts the market's players roughly when the market drafts them", async () => {
    // The ADP half of the blend. Of the 40 players the market ranks highest, how many are gone by
    // the end of round 4 (48 picks)? Chance alone — a room drafting on our synthetic board order,
    // which is independent of ADP here — would take 40 × 48/858 ≈ 2.2.
    //
    // MEASURED on the committed fixture, seeds 1..12: 18, 24, 20, 24, 25, 18, 21, 22, 22, 21, 20,
    // 21 — i.e. 18-25, roughly ten times chance. The floor is set at 12: below the observed
    // minimum, so tuning the persona spread does not churn it, and far enough above chance that an
    // implementation ignoring ADP cannot reach it.
    //
    // ⚠️ 18-25 of 40 is NOT a portrait of how a real room drafts, and should not be read as one.
    // It is DILUTED by the very fixture property that makes this test discriminating: our board
    // order here is random noise, so a persona's projection half actively fights its market half.
    // On the served board the two orders agree closely and the market's top 40 clear far faster.
    // Raising this floor toward a realistic figure would therefore be pinning a fixture artifact.
    const b = board()
    const market = marketOrder(b)
    const topMarket = new Set(
      b.filter((p) => p.adp != null).sort((x, y) => (x.adp as number) - (y.adp as number)).slice(0, 40).map((p) => p.id),
    )
    expect(topMarket.size, "the fixture no longer carries an ADP sample").toBe(40)

    for (const seed of [1, 2, 3, 4, 5, 6, 7, 8]) {
      const early = fullRoom(seed).picks.slice(0, 48)
      const taken = early.filter((p) => topMarket.has(p.id)).length
      expect(
        taken,
        `seed ${seed}: only ${taken} of the market's top 40 were gone after four rounds — the CPU is not reading ADP`,
      ).toBeGreaterThanOrEqual(12)
    }

    // …and not SLAVISHLY. A room that drafted pure ADP would take the top 48 by market rank in
    // almost exactly that order; real rooms do not, and neither should this one.
    const first48 = fullRoom(11).picks.slice(0, 48).map((p) => market.get(p.id) ?? 1e9)
    const inMarketOrder = first48.every((r, i) => i === 0 || first48[i - 1] <= r)
    expect(inMarketOrder, "the room drafted in exact ADP order — there is no variance in the sim").toBe(false)
  })

  test("the room also drafts off OUR board where the market has no view", async () => {
    // The other half of the blend, and the half a pure-ADP implementation would fail outright. 632
    // of the 858 fixture rows sit outside the ADP sample; drawing among them at random would give a
    // median board rank around the middle of that pool (~316). If our projections are driving those
    // picks, the median lands near the TOP of the board instead.
    //
    // MEASURED (10 rounds, 12 teams, seeds 1..12): 13-34 off-sample picks per room, with a median
    // `ovrRank` of 13-21 — an order of magnitude better than chance. Floors set at >5 picks and a
    // median <100, both well clear of the observed range and both unreachable by a random draw.
    const b = board()
    const brd = boardOrder(b)
    const adp = new Map(b.map((p) => [p.id, p.adp]))
    const picks = fullRoom(7).picks
    const offSample = picks.filter((p) => adp.get(p.id) == null).map((p) => brd.get(p.id) as number)

    expect(
      offSample.length,
      "no un-ADP'd player was drafted at all — the sim cannot see past the market sample",
    ).toBeGreaterThan(5)
    const sorted = [...offSample].sort((x, y) => x - y)
    const median = sorted[Math.floor(sorted.length / 2)]
    expect(
      median,
      `the median board rank of an off-sample pick was ${median} — no better than drawing at random, so our projections are not being read`,
    ).toBeLessThan(100)
  })

  test("every CPU pick is legal for the roster that made it, and nobody is drafted twice", async () => {
    // A room that drafts three kickers, or the same player for two teams, is not a practice
    // opponent — and the grade compares the user against these rosters, so an illegal one silently
    // corrupts the only number the results screen shows.
    const c = config()
    const b = board()
    const byId = new Map(b.map((p) => [p.id, p]))
    const picks = fullRoom(3).picks

    const seen = new Set<string>()
    const held = new Map<number, Player[]>()
    picks.forEach((pick, i) => {
      expect(seen.has(pick.id), `pick ${i + 1} drafted ${pick.id}, who was already taken`).toBe(false)
      seen.add(pick.id)

      const player = byId.get(pick.id) as Player
      const roster = held.get(pick.slot) ?? []
      // The check is made against the roster AS IT WAS before the pick — the same question the
      // engine asked itself.
      expect(
        openEligibility(roster, c.roster).has(player.pos),
        `pick ${i + 1}: team ${pick.slot} drafted a ${player.pos} with no slot left that accepts one`,
      ).toBe(true)
      held.set(pick.slot, [...roster, player])
    })
  })
})

// ── the loop, in the browser ────────────────────────────────────────────────────────────────────

/** Sign in as a subscriber and start a quick mock from draft slot 4 — deliberately NOT slot 1, so
 *  the room has to make eleven picks before the user's first turn and "the CPU actually picks" is a
 *  reachable question. */
async function startMock(page: Page) {
  const errors = collectPageErrors(page)
  await signIn(page, { groups: ["subscriber"] })
  await mockApi(page, { entitlement: "entitled", leagues: "none" })
  await page.goto("/fantasy/mock-draft")

  await expect(page.getByRole("heading", { name: "Mock Draft" })).toBeVisible()

  // The setup screen's copy is returned rather than screened here, because it is the ONLY screen
  // that stops existing once the draft starts — a denylist scan run at the end can never see it.
  const setupText = await page.evaluate(() => document.body.innerText)

  // ⚠️ A Radix `Picker`, not a native <select> — `selectOption` silently does nothing on one.
  await page.getByLabel("My draft slot").click()
  await page.getByRole("option", { name: "Pick 4", exact: true }).click()

  await page.getByRole("button", { name: "Start mock draft" }).click()
  await expect(page.locator("table tbody tr").first()).toBeVisible()
  return { errors, setupText }
}

/** The draft's phase, read in ONE round trip.
 *
 *  ⚠️ READ WITH `evaluate`, NOT WITH A COMPOSED LOCATOR, and the reason is measured rather than
 *  stylistic. The previous cut waited on `myTurn.or(grade).or(skip).first()` and timed out on CI
 *  **while the page snapshot in the failure artifact contained "You're on the clock"** — and while
 *  the two sibling tests that wait on the very same text with a PLAIN locator passed in the same
 *  run. So the text was there and the un-composed locator finds it; only the `or()`-composed one
 *  reported nothing. Rather than litigate Playwright's composition semantics on a surface that has
 *  three legitimate next states, ask the DOM once and branch on the answer.
 *
 *  The apostrophe is a character class because the copy is one editorial pass away from becoming a
 *  typographic ’, which would silently make a `'`-spelled regex match nothing. */
async function readPhase(page: Page): Promise<"graded" | "my-turn" | "cpu" | "unknown"> {
  return page.evaluate(() => {
    if (document.querySelector('[data-testid="mock-draft-grade"]')) return "graded" as const
    const text = document.body.innerText
    if (/You['’]re on the clock/.test(text)) return "my-turn" as const
    if (/Skip to my pick/.test(text)) return "cpu" as const
    return "unknown" as const
  })
}

/** Drive the mock to completion: take the top recommendation on every turn, fast-forward the room
 *  in between.
 *
 *  ⭐ A STATE MACHINE OVER ONE PHASE READ, re-entered every iteration — not "wait for my turn, then
 *  wait for the fast-forward". Two separate waits stall: the fast-forward click can miss (the
 *  button detaches when the room finishes a round underneath it), and the next iteration would then
 *  be waiting for a turn that only the 70ms-per-pick reveal timer can deliver. Re-reading the phase
 *  makes a missed click cost one iteration.
 *
 *  ⚠️ ALSO NOT A POLL-AND-SLEEP. The first cut was a 60-step loop that re-read three locators and
 *  slept 200ms whenever it caught the page mid-render — fine on a laptop, and still looping when
 *  the 60s test timeout fired on a CI runner, which surfaces as the thoroughly unhelpful
 *  `locator.count: Target page, context or browser has been closed`.
 *
 *  The bound is generous (~3 iterations per user pick) because it exists to stop a genuine hang
 *  spinning, not to schedule the draft; the caller's assertion is what reports the outcome. */
async function playToTheEnd(page: Page, rounds = 8) {
  for (let i = 0; i < rounds * 3 + 6; i++) {
    await expect
      .poll(() => readPhase(page), {
        message: "the mock reached no recognisable state — not the user's turn, not graded, no fast-forward",
        timeout: 30_000,
      })
      .not.toBe("unknown")

    const phase = await readPhase(page)
    if (phase === "graded") return
    if (phase === "my-turn") {
      await page.getByRole("button", { name: "Draft", exact: true }).first().click()
      continue
    }
    // A fast-forward click can miss — the button detaches when the room finishes a round underneath
    // it. Swallowing it is safe because the loop simply re-reads the phase and tries again.
    await page.getByRole("button", { name: /Skip to my pick/ }).click().catch(() => {})
  }
}

test.describe("running a mock draft", () => {
  // ⏱️ The two tests that play a mock out drive ~96 picks through a real React state machine.
  // `test.slow()` triples this file's budget rather than raising the global timeout, which would
  // hide a genuine hang everywhere else.
  //
  // ⚠️ THE BUDGET IS NOT WHAT MADE THIS FILE RED ON CI, and the distinction cost a round trip to
  // find. Raising it 60s → 180s did NOT fix the CI failure: the draft was not running slowly, it
  // was not running AT ALL — the failure artifact's page snapshot showed it still at Round 1 Pick 4
  // after the full timeout, because the composed locator the loop waited on never matched (see
  // `readPhase`). A budget increase makes a stall take longer to report; it never cures one.
  //
  // Measured, once the phase read was fixed: clean at `--workers=2 --repeat-each=3` (the gate, and
  // what CI runs). At `--workers=8` on a laptop about 1 in 10 still exhausts the budget, with the
  // teardown signature (`page.evaluate: Target page … has been closed`) rather than a stalled
  // screen — eight browsers against one `next start` is the rig running out of machine, not the
  // app. Judge this file at the gate's settings.
  test.slow()

  test("the CPU room picks before the user's turn, and its picks are explained", async ({ page }) => {
    const { errors } = await startMock(page)

    // ⭐ THE FEATURE'S WHOLE PREMISE. Nobody has to type in what the room did.
    await expect(
      page.getByRole("heading", { name: "Draft log" }),
      "the room made no picks at all before the user's first turn",
    ).toBeVisible()

    // EXACTLY three, and the exactness is the point: from draft slot 4 the seats ahead of the user
    // are 1, 2 and 3, so a room that made two has stalled and a room that made four has drafted
    // THROUGH the user's turn — the failure that would quietly pick the user's team for them.
    await expect
      .poll(async () => page.getByText(/^T\d+$/).count(), {
        message: "the opponent picks before the user's first turn are not the three seats ahead of them",
      })
      .toBe(3)
    await expect(
      page.getByText(/Round 1 · Pick 4/),
      "the clock is not on the user's first-round pick after the room drafted ahead of them",
    ).toBeVisible()

    // Each opponent pick carries the reason it was made. A room that picks without saying why is
    // the market-replay product this feature exists NOT to be.
    await expect
      .poll(
        async () =>
          (await page.getByRole("heading", { name: "Draft log" }).locator("xpath=..").innerText()).match(
            /ADP|starter|need|FLEX|sample/gi,
          )?.length ?? 0,
        { message: "no opponent pick in the log states why it was made" },
      )
      .toBeGreaterThan(0)

    await expect(page.getByText(/You're on the clock/)).toBeVisible()
    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("our recommendations render with their reasoning while the mock runs", async ({ page }) => {
    const { errors } = await startMock(page)
    await expect(page.getByText(/You're on the clock/)).toBeVisible()

    await expect(
      page.getByRole("heading", { name: /Recommended picks/ }),
      "the recommendation panel is missing on the user's own turn",
    ).toBeVisible()

    // ⭐ THE DIFFERENTIATOR IS THE "WHY", so assert the rationale is THERE, not just the names.
    // `recommend` always produces one (it falls through to "Best value on the board (VOR)"), so an
    // empty rationale column means the panel is rendering something other than our engine's output.
    const panel = page.getByRole("heading", { name: /Recommended picks/ }).locator("xpath=../..")
    await expect
      .poll(
        async () =>
          (await panel.innerText()).match(/Best value on the board|Fills your open|Fills an open FLEX|VOR cliff|Depth pick/g)
            ?.length ?? 0,
        { message: "the recommendations rendered without any reasoning beside them" },
      )
      .toBeGreaterThan(0)

    expectNoPageErrors(errors)
  })

  test("a full quick mock runs to completion and the roster grades", async ({ page }) => {
    const { errors } = await startMock(page)
    await playToTheEnd(page)

    const grade = page.getByTestId("mock-draft-grade")
    await expect(grade, "the mock never reached a graded finish").toBeVisible()

    // ⭐ THE RANK MUST NAME ITS OWN MEASURE IN THE SAME BREATH (NF-C6P3). A bare "4th of 12" is read
    // by every user as a projected league finish; that is the overclaim this wording exists to
    // prevent, and it is one careless copy edit away at all times.
    await expect(
      grade.getByText(/\d+(st|nd|rd|th) of \d+ in this mock room on projected starter points/),
      "the finishing rank is rendered without naming the measure it is a rank ON",
    ).toBeVisible()

    // ⚠️ AND THE CIRCULARITY CAVEAT, VERBATIM AND UNCONDITIONAL — not behind a click, not a tooltip.
    // The room is scored on the same projections the recommendations maximise, so a good finish is
    // partly built in; a grade that ships without saying so is an overclaim.
    await expect(
      grade.getByText(GRADE_CIRCULARITY_NOTE, { exact: false }),
      "the grade shipped without the note saying it scores the room on our own projections",
    ).toBeVisible()

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("nothing on the mock draft claims an edge over the market", async ({ page }) => {
    // best_alpha = 0. The denylist is the shared mirror of the exporter's own list, so a phrase
    // added there is enforced here too.
    //
    // ⚠️ ALL THREE SCREENS, because they are three different bodies of copy and the results screen
    // is the one most likely to grow a claim. The setup screen has to be captured before the draft
    // starts — it is gone by the time the grade renders.
    const { errors, setupText } = await startMock(page)
    expect(
      forbiddenPhrasesIn(setupText),
      "the mock draft SETUP screen makes a claim the denylist forbids",
    ).toEqual([])

    const draftText = await page.evaluate(() => document.body.innerText)
    expect(
      forbiddenPhrasesIn(draftText),
      "the mock draft BOARD makes a claim the denylist forbids",
    ).toEqual([])

    await playToTheEnd(page)
    await expect(page.getByTestId("mock-draft-grade")).toBeVisible()

    const gradedText = await page.evaluate(() => document.body.innerText)
    expect(
      forbiddenPhrasesIn(gradedText),
      "the mock draft RESULTS screen makes a claim the denylist forbids",
    ).toEqual([])
    expectNoPageErrors(errors)
  })
})
