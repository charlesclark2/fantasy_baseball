import { expect, test, type Page } from "@playwright/test"
import { FIXTURES, collectPageErrors, mockApi } from "../support/api-mock"
import { signIn } from "../support/session"
import { expectApiFullyMocked, expectNoNaN, expectNoPageErrors } from "../support/assertions"
import { recommend, type LeagueConfigMeta, type Player } from "@/lib/draft-optimizer"

/**
 * E9.64 — THE DRAFT OPTIMIZER, DRIVEN.
 *
 * ══ WHY THIS IS THE BIGGEST GAP IN THE SUITE ══════════════════════════════════════════════════
 *
 * It is the paid product's decision-support half — the thing a membership is actually bought for —
 * it is the largest component in the app, and before this file NOTHING anywhere opened it. Every
 * other fantasy surface is a rendered read; this one is a STATE MACHINE the user drives for two
 * hours while their draft is happening, and its failures are the kind no static gate can see:
 *
 *   · a drafted player who stays on the board, so he can be taken twice
 *   · a clock that does not advance, or advances to the wrong team (snake order is arithmetic)
 *   · a sort that re-orders the rows but not the values, or that silently sorts the STRING
 *   · Undo that removes the wrong pick
 *   · a board that survives a reload but loses the picks (people reload mid-draft; the whole point
 *     of persisting to localStorage is that the tab can die at pick 40)
 *
 * ⚠️ WHO CAN OPEN IT is asserted in `fantasy-entitlement-gates.spec.ts`, not here. This file signs
 * in as a subscriber and asks only whether the tool WORKS.
 *
 * ⚠️ ASSERT AGAINST THE SERVED BOARD, never against a name — the board is republished constantly.
 */

/** The draft screen renders exactly one `<table>`: the available-players board. The roster panel and
 *  the recent-picks list are `div`s.
 *
 *  ⭐ PINNED RATHER THAN ASSUMED. If a future change adds a second table, an unqualified
 *  `page.locator("table")` would start resolving to whichever came first and every assertion below
 *  would quietly describe the wrong element. `assertOneBoard` makes that a loud failure instead. */
async function assertOneBoard(page: Page) {
  await expect(
    page.locator("table"),
    "the draft screen grew a second table — the locators in this file now need scoping",
  ).toHaveCount(1)
}

type Row = { id: string; name: string; pts: number | null; vor: number | null }

/** The available board as data: id, name and both sortable columns. */
async function availableRows(page: Page): Promise<Row[]> {
  return page.locator("table tbody tr").evaluateAll((rows) =>
    rows.map((r) => {
      const cells = Array.from(r.children) as HTMLElement[]
      const link = r.querySelector('a[href^="/fantasy/player/"]') as HTMLAnchorElement | null
      const numeric = (el: HTMLElement | undefined) => {
        const t = (el?.textContent ?? "").trim()
        return t === "" || t === "—" ? null : Number(t)
      }
      return {
        id: (link?.getAttribute("href") ?? "").split("/").pop() ?? "",
        name: (link?.textContent ?? "").trim(),
        pts: numeric(cells[2]),
        vor: numeric(cells[3]),
      }
    }),
  )
}

/** Sign in as a subscriber, open the optimizer and start a draft on the default preset. */
async function startDraft(page: Page) {
  const errors = collectPageErrors(page)
  await signIn(page, { groups: ["subscriber"] })
  const mock = await mockApi(page, { entitlement: "entitled", leagues: "none" })
  await page.goto("/fantasy/draft")

  await expect(page.getByRole("heading", { name: "Draft Optimizer" })).toBeVisible()
  await page.getByRole("button", { name: "Start draft" }).click()

  await expect(page.locator("table tbody tr").first()).toBeVisible()
  await assertOneBoard(page)
  return { errors, mock }
}

// ══════════════════════════════════════════════════════════════════════════════════════════════
// THE FLEX SEAT — asserted on the engine, with no browser
// ══════════════════════════════════════════════════════════════════════════════════════════════
//
// ⭐ REPORTED OFF A REAL MOCK DRAFT (operator, 2026-08-17): "it seemed to really be pushing for TEs
// to fill my FLEX spot, which seems unrealistic unless they're projected to outscore RBs and WRs,
// which in the middle rounds, that shouldn't be a safe assumption." It was, and the cause was that
// VOR — points over YOUR OWN POSITION's replacement — is not a fair comparator for a seat that will
// take any of three positions. On the served 2026 board, TE replacement sits 17.9-19.7 points below
// RB/WR replacement, so every TE carried that much of a head start into a flex comparison he does
// not deliver in the lineup. `recommend` now scores a flex-only candidate against the SEAT's
// replacement instead. See the long note in `draft-optimizer.ts`.
//
// ⚠️ ENGINE-LEVEL AND HAND-BUILT, on purpose. The committed fixture's `pts`/`vor`/`repl` are
// SYNTHETIC (seeded off player id), so it cannot be relied on to reproduce the real board's
// replacement-level gap — and the rendered panel would only ever tell you that SOME name is on top,
// which is precisely how this shipped. These boards make the mechanism unambiguous: whichever
// player projects more POINTS is stated in the fixture itself, so each assertion has a right answer
// that does not depend on the engine agreeing with itself.
//
// ⚠️ EACH CLAUSE GETS ITS OWN FIXTURE (the NF-D17 lesson). The rule is an `and` over several
// conditions, so a single fixture that trips more than one of them would prove none of them: the
// three tests below differ in exactly one input each, and each is RED-proven separately.

const FLEX_ROSTER = [
  { name: "QB", count: 1, eligible: ["QB"], bench: false },
  { name: "RB", count: 2, eligible: ["RB"], bench: false },
  { name: "WR", count: 2, eligible: ["WR"], bench: false },
  { name: "TE", count: 1, eligible: ["TE"], bench: false },
  { name: "FLEX", count: 1, eligible: ["RB", "WR", "TE"], bench: false },
  { name: "BN", count: 6, eligible: ["QB", "RB", "WR", "TE"], bench: true },
]

const flexConfig = (): LeagueConfigMeta => ({
  name: "flex_probe",
  label: "Flex probe",
  ppr: "full",
  superflex: false,
  description: "",
  roster: FLEX_ROSTER,
})

/** `repl` is a per-position constant on the real board, so it is one here too. The gap between
 *  them is the whole mechanism: a flex seat's fallback is a startable RB (100), never a startable
 *  TE (80), so a TE's published VOR flatters him by 20 points for this seat and no other. */
const REPL = { QB: 200, RB: 100, WR: 100, TE: 80 } as const

function probePlayer(id: string, pos: keyof typeof REPL, pts: number): Player {
  return {
    id,
    name: id,
    pos,
    team: "AAA",
    bye: 7,
    rookie: false,
    g: 17,
    pts,
    repl: REPL[pos],
    vor: pts - REPL[pos],
    posRank: 1,
    ovrRank: 1,
    vorP10: null,
    vorP90: null,
    ptsP10: null,
    ptsP90: null,
    adp: null,
    lowPred: false,
    predNote: null,
  }
}

/** `tePts` is the only knob. Everything else is fixed, so each test differs in one number. */
function probeBoard(tePts: number): Player[] {
  return [
    probePlayer("qb1", "QB", 260),
    probePlayer("rb1", "RB", 128),
    probePlayer("rb2", "RB", 112),
    probePlayer("wr1", "WR", 130),
    probePlayer("wr2", "WR", 126),
    probePlayer("wr3", "WR", 124),
    // A steep TE cliff behind him — the shape that used to buy the seat outright.
    probePlayer("te1", "TE", tePts),
    probePlayer("te2", "TE", 90),
  ]
}

test.describe("the FLEX seat is scored on points, not on a position's own replacement", () => {
  /** Every dedicated starter filled by players who are NOT the candidates under test — QB, 2x RB,
   *  2x WR and (optionally) a TE — so the FLEX is the only skill seat open and rb1/wr1/te1 compete
   *  for it directly. */
  function stateWith(tePts: number, opts: { teStarterFilled: boolean }) {
    const board = probeBoard(tePts)
    const filler: Player[] = [
      probePlayer("f_qb", "QB", 255),
      probePlayer("f_rb_a", "RB", 108),
      probePlayer("f_rb_b", "RB", 106),
      probePlayer("f_wr_a", "WR", 118),
      probePlayer("f_wr_b", "WR", 116),
      ...(opts.teStarterFilled ? [probePlayer("f_te", "TE", 84)] : []),
    ]
    const mine = filler.map((p) => p.id)
    return {
      board: [...board, ...filler],
      config: flexConfig(),
      draftedIds: new Set(mine),
      myPlayerIds: mine,
      picksRemaining: 8,
      limit: 20,
    }
  }

  test("a TE who projects FEWER points than an available WR does not win the FLEX seat", () => {
    // te1 = 122 pts (VOR 42, because TE replacement is 80). wr1 = 130 pts (VOR 30).
    // The TE's VOR is 12 higher; the WR puts 8 more points in the seat. The seat gets the points.
    const recs = recommend(stateWith(122, { teStarterFilled: true }))
    const top = recs[0]
    expect(
      recs.length,
      "no candidates came back — this test would assert on nothing",
    ).toBeGreaterThan(3)
    expect(
      top.player.pos,
      `the top pick for a FLEX-only roster was ${top.player.name} (${top.player.pos}, ` +
        `${top.player.pts} pts) over a WR projected for 130 — the flex seat is being scored on ` +
        `each position's own replacement again`,
    ).not.toBe("TE")
    expect(top.player.id).toBe("wr1")

    // ...and the TE is not merely demoted, he is demoted BY THE RIGHT AMOUNT: his seat value is
    // points over the seat's replacement (122 - 100), not over his position's (122 - 80).
    const te = recs.find((r) => r.player.id === "te1")!
    expect(te.needLevel, "te1 should be a FLEX-only candidate in this state").toBe(1)
    expect(te.seatValue).toBeCloseTo(22, 5)
    expect(te.player.vor).toBeCloseTo(42, 5)
  })

  test("a TE who DOES out-project the flex pool still wins the seat", () => {
    // The operator's own criterion, stated positively — and the clause that stops anyone
    // "fixing" the report above by simply penalising tight ends.
    const recs = recommend(stateWith(140, { teStarterFilled: true }))
    expect(recs[0].player.id, "a TE projected for 140 lost a flex seat to a WR projected for 130").toBe(
      "te1",
    )
  })

  test("the DEDICATED TE starter is untouched — the same TE wins it on his full VOR", () => {
    // Identical board to the first test. The ONLY difference is that the TE starter is open, so the
    // seat is a TE seat and TE-vs-TE is exactly what VOR is for. If this ever goes red alongside the
    // first test, the change has become a blanket TE penalty rather than a statement about a seat.
    const recs = recommend(stateWith(122, { teStarterFilled: false }))
    const te = recs.find((r) => r.player.id === "te1")!
    expect(te.needLevel, "with no TE rostered the TE slot should be a dedicated need").toBe(2)
    expect(te.seatValue, "a dedicated-slot candidate must keep his published VOR").toBeCloseTo(42, 5)
    expect(recs[0].player.id, "the best TE lost his own open TE starter slot").toBe("te1")
  })

  test("flex urgency is the gap over the FLEX POOL, not the gap to the next man at the position", () => {
    // ⚠️ THE HALF THAT MEASURED INERT, pinned anyway. On the served board, reverting this rule alone
    // changes the top recommendation on 0 of 3,000 decision points — the flex bonus is capped by
    // `NEED_W_FLEX` at a few VOR and the gaps it competes with are far wider. So it cannot be
    // RED-proven through a flipped pick, and asserting on a pick would be a clause that cannot fail.
    // It is asserted on the QUANTITY instead, where it is unambiguous.
    //
    // wr1 leads the flex pool at 30 seat-points. Behind him in the POOL is rb1 at 28 → a gap of 2,
    // so the bonus is 0.4 x 2 = 0.8. Behind him at his own POSITION is wr2 at 26 → a gap of 4, which
    // is what the old rule used and would have paid 1.6 for.
    const recs = recommend(stateWith(122, { teStarterFilled: true }))
    const wr = recs.find((r) => r.player.id === "wr1")!
    expect(wr.needLevel, "wr1 should be a FLEX-only candidate in this state").toBe(1)
    expect(wr.positionalDropoff, "the within-position gap should still be reported as 4").toBeCloseTo(4, 5)
    expect(
      wr.needBonus,
      "the flex bonus was paid on the within-position gap (1.6) rather than the flex-pool gap (0.8)",
    ).toBeCloseTo(0.8, 5)
  })

  test("the reason shown never quotes a number the score did not use", () => {
    const recs = recommend(stateWith(122, { teStarterFilled: true }))
    const te = recs.find((r) => r.player.id === "te1")!
    // The re-basing moved his score by 20 points, so it has to be on screen: a panel that shows a
    // score 20 below the VOR the rest of the site publishes, with no explanation, is a number a
    // user is right not to trust.
    expect(
      te.rationale,
      `te1 was re-based by ${Math.round((te.player.vor ?? 0) - te.seatValue)} points and the reason ` +
        `given was "${te.rationale}"`,
    ).toContain("FLEX seat's replacement")
    // ⛔ And the within-position cliff must NOT be quoted as the flex bonus's source: te1 sits 32
    // VOR above te2, and citing that gap beside a bonus computed from the flex pool would explain
    // the score with a number the score never touched.
    expect(te.rationale).not.toContain("VOR over the next TE")
  })
})

test.describe("setting up and starting a draft", () => {
  test("the board opens on the chosen league with real numbers and a clock at pick one", async ({
    page,
  }) => {
    const { errors, mock } = await startDraft(page)

    const rows = await availableRows(page)
    expect(rows.length, "the available board rendered no players").toBeGreaterThan(20)
    // ⭐ Both sortable columns carry real values. A board of names with empty Pts/VOR columns
    // renders perfectly and is useless — and `—` is what a null renders as, so it would pass any
    // "the table has rows" assertion.
    expect(
      rows.filter((r) => r.pts != null).length,
      "the Pts column is empty — the board rendered names and no projections",
    ).toBeGreaterThan(20)
    expect(
      rows.filter((r) => r.vor != null).length,
      "the VOR column is empty — the value-over-replacement the tool exists to compute is missing",
    ).toBeGreaterThan(20)

    // The clock. Slot 1 on pick 1 of a snake is the user's own turn, which is what the whole
    // recommendation panel keys on.
    await expect(page.getByText(/Round 1 · Pick 1/)).toBeVisible()
    await expect(
      page.getByText(/Your pick — choose a player below/),
      "the optimizer did not know it was the user's turn on their own first-round pick",
    ).toBeVisible()

    await expectNoNaN(page)
    expectApiFullyMocked(mock)
    expectNoPageErrors(errors)
  })

  test("the recommendations come off the board that is actually loaded", async ({ page }) => {
    // A recommendation panel populated from anywhere other than the loaded board — a stale closure,
    // a different config — renders plausibly and advises on players who are not in this draft.
    const { errors } = await startDraft(page)
    const boardIds = new Set((FIXTURES.boardFree() as any[]).map((p) => p.id))

    // ⏳ An auto-retrying assertion, never `await locator.count()`. The panel is React state settling
    // after the board query resolves, so a single-shot read races it — the G100-D0-R1 flake exactly
    // (one commit, two runs minutes apart, one red one green).
    await expect(
      page.getByRole("heading", { name: /Recommended picks/ }),
      "the recommendation panel is missing on the user's own turn",
    ).toBeVisible()

    // Every player offered on the board is a player the served payload contains.
    const rows = await availableRows(page)
    const foreign = rows.filter((r) => !boardIds.has(r.id))
    expect(
      foreign.slice(0, 5).map((r) => r.name),
      "the board is offering players that are not in the payload it was served",
    ).toEqual([])
    expectNoPageErrors(errors)
  })
})

test.describe("tracking picks", () => {
  test("drafting a player takes him off the board and moves the clock on", async ({ page }) => {
    const { errors } = await startDraft(page)

    const before = await availableRows(page)
    const target = before[0]

    // On the user's own turn the row button reads "Draft"; on someone else's it reads "→ T<n>".
    await page.locator("table tbody tr").first().getByRole("button").click()

    // ⭐ HE MUST LEAVE THE BOARD. A drafted player who stays can be taken twice, and in a live draft
    // that is discovered by the room rather than by us.
    await expect
      .poll(async () => (await availableRows(page)).map((r) => r.id), {
        message: `${target.name} was drafted and is still on the available board`,
      })
      .not.toContain(target.id)

    // …and he must land somewhere the user can see. "Recent picks" is the audit trail the whole
    // session depends on; a pick that vanishes from both lists is indistinguishable from a misclick.
    await expect(
      page.getByText("Recent picks").locator("xpath=..").getByText(target.name, { exact: false }),
      `${target.name} was drafted but appears in no pick list`,
    ).toBeVisible()

    // The clock advances, and it is no longer the user's turn — slot 1 does not pick twice in a row.
    await expect(page.getByText(/Round 1 · Pick 2/)).toBeVisible()
    await expect(
      page.getByText(/Your pick — choose a player below/),
      "the optimizer still thinks it is the user's turn after they used their pick",
    ).toHaveCount(0)

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("Undo returns the last pick to the board and rewinds the clock", async ({ page }) => {
    const { errors } = await startDraft(page)
    const target = (await availableRows(page))[0]

    await page.locator("table tbody tr").first().getByRole("button").click()
    await expect(page.getByText(/Round 1 · Pick 2/)).toBeVisible()

    await page.getByRole("button", { name: "Undo" }).click()

    // Both halves, because they fail independently: a rewind that restores the clock but not the
    // board leaves a player permanently missing from a two-hour draft.
    await expect
      .poll(async () => (await availableRows(page)).map((r) => r.id), {
        message: `Undo did not return ${target.name} to the board`,
      })
      .toContain(target.id)
    await expect(
      page.getByText(/Round 1 · Pick 1/),
      "Undo restored the player but left the clock on the next pick",
    ).toBeVisible()

    expectNoPageErrors(errors)
  })

  test("a mid-draft reload keeps the picks", async ({ page }) => {
    // ⭐ THE REASON THE STATE IS PERSISTED AT ALL. A draft runs for two hours in a tab that gets
    // reloaded, backgrounded and killed; losing the tracked picks at pick 40 is losing the session.
    // Nothing else in the suite reloads anything.
    const { errors } = await startDraft(page)
    const target = (await availableRows(page))[0]
    await page.locator("table tbody tr").first().getByRole("button").click()
    await expect(page.getByText(/Round 1 · Pick 2/)).toBeVisible()

    await page.reload()
    await page.getByRole("button", { name: "Start draft" }).click()
    await expect(page.locator("table tbody tr").first()).toBeVisible()

    await expect(
      page.getByText(/Round 1 · Pick 2/),
      "the tracked picks did not survive a reload — a two-hour session is one refresh from gone",
    ).toBeVisible()
    expect(
      (await availableRows(page)).map((r) => r.id),
      "the drafted player came back onto the board after a reload",
    ).not.toContain(target.id)

    expectNoPageErrors(errors)
  })
})

test.describe("finding a player on the board", () => {
  test("the Pts column sorts by points, and clicking again reverses it", async ({ page }) => {
    const { errors } = await startDraft(page)

    await page.getByRole("button", { name: /^Pts/ }).click()

    // ⚠️ K AND D/ST ARE DEFERRED TO THE BOTTOM BY DESIGN (`deferLowPred`) unless their own tab is
    // selected, so the ordering claim holds over the SKILL players — asserting over every row would
    // fail on a correct board and send the next reader at the sort code. Positions come from the
    // served payload rather than from the rendered badge.
    const pos = new Map((FIXTURES.boardFree() as any[]).map((p) => [p.id, p.pos]))
    const skillPts = (rows: Row[]) =>
      rows.filter((r) => !["K", "DST"].includes(pos.get(r.id) ?? "") && r.pts != null).map((r) => r.pts!)

    await expect
      .poll(
        async () => {
          const v = skillPts(await availableRows(page))
          return v.length > 1 && v.every((x, i) => i === 0 || v[i - 1] >= x)
        },
        { message: "sorting by Pts did not put the column in descending order" },
      )
      .toBe(true)

    // The toggle. A header that sorts one way and then does nothing is a control that looks live
    // and is not — and it is the natural bug, because the direction state is separate.
    await page.getByRole("button", { name: /^Pts/ }).click()
    await expect
      .poll(
        async () => {
          const v = skillPts(await availableRows(page))
          return v.length > 1 && v.every((x, i) => i === 0 || v[i - 1] <= x)
        },
        { message: "clicking Pts a second time did not reverse the sort" },
      )
      .toBe(true)

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("the position tabs and the search box both narrow the board", async ({ page }) => {
    const { errors } = await startDraft(page)
    const pos = new Map((FIXTURES.boardFree() as any[]).map((p) => [p.id, p.pos]))

    await page.getByRole("button", { name: "TE", exact: true }).click()
    await expect.poll(async () => (await availableRows(page)).length).toBeGreaterThan(0)

    const filtered = await availableRows(page)
    const wrong = filtered.filter((r) => pos.get(r.id) !== "TE")
    expect(
      wrong.slice(0, 5).map((r) => r.name),
      `the TE tab kept ${wrong.length} players who are not tight ends in the served board`,
    ).toEqual([])

    // Search composes with the filter rather than replacing it — the two are separate state and
    // an implementation that resets one on the other is a real, quiet annoyance mid-draft.
    const target = filtered[0]
    await page.getByPlaceholder("Search…").fill(target.name)
    await expect
      .poll(async () => (await availableRows(page)).map((r) => r.id), {
        message: `searching "${target.name}" inside the TE tab lost his row`,
      })
      .toContain(target.id)

    const searched = await availableRows(page)
    expect(
      searched.filter((r) => pos.get(r.id) !== "TE").slice(0, 5).map((r) => r.name),
      "searching inside a position tab escaped the filter",
    ).toEqual([])

    expectNoPageErrors(errors)
  })
})
