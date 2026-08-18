import { readFileSync } from "node:fs"
import { join } from "node:path"
import { expect, test, type Page } from "@playwright/test"
import { collectPageErrors, mockApi } from "../support/api-mock"
import { signIn } from "../support/session"
import { expectNoNaN, expectNoPageErrors } from "../support/assertions"
import {
  EMPTY_DOC,
  MAX_NOTE_LEN,
  applyDoc,
  baseOrder,
  cheatSheet,
  customTiers,
  divergence,
  moveTo,
  ourTierBreaks,
  reconcile,
  setNote,
  setTag,
  toggleTierBreak,
  type BigBoardDoc,
} from "@/lib/big-board"
import { sortAvailable, type Player } from "@/lib/draft-optimizer"
import { FANTASY_SEASON as SEASON } from "@/lib/fantasy-queries"

/**
 * NF-C4 — THE CUSTOM BIG BOARD.
 *
 * Two halves, and both are load-bearing for different reasons.
 *
 * ══ 1. THE ORDERING MATH ═══════════════════════════════════════════════════════════════════════
 *
 * A saved board stores an explicit PREFIX and rebuilds the tail from whatever board is published
 * today. That buys three things at once (see `lib/big-board.ts`) and costs one: the reconstruction
 * has to be EXACT, or a user's printed cheat sheet disagrees with the screen it came from. So the
 * identity is asserted over a GRID of moves rather than at a few hand-picked points — the failure
 * mode is an off-by-one at the trim boundary, which chosen examples are the wrong instrument for.
 *
 * ⚠️ RUN AGAINST THE REAL PUBLISHED BOARD FIXTURE (858 rows), not a toy: the trim only has anything
 * to trim on a board long enough for a move to leave a tail.
 *
 * ══ 2. THE BROWSER ════════════════════════════════════════════════════════════════════════════
 *
 * Everything here fails silently in production if it fails at all: a drag that does not commit, a
 * save that reports success without landing, a board that reloads as ours. The reload assertions
 * drive a REAL round trip through a stateful mock (see `customBoardResponse`) — an echoing stub
 * would pass against a client that never sent anything, which is the vacuous shape a persistence
 * test is most likely to have.
 */

// ── the board fixture, as `Player[]` ─────────────────────────────────────────────────────────────

const BOARD: Player[] = JSON.parse(
  readFileSync(
    join(process.cwd(), "e2e", "fixtures", "api", "fantasy-nfl-board-full_ppr-12-2026-free.json"),
    "utf8",
  ),
)

const ids = (rows: Player[]) => rows.map((p) => p.id)

test.describe("the stored prefix reconstructs the user's board exactly", () => {
  test("the fixture is a real, long board — otherwise nothing below tests the tail", () => {
    // ⚠️ ANTI-VACUITY FIRST. Every clause here indexes into this array; a short or empty fixture
    // would make each of them pass on nothing (NF1.7(a)).
    expect(BOARD.length).toBeGreaterThan(500)
    expect(new Set(ids(BOARD)).size).toBe(BOARD.length)

    // 🔴 MEASURED, AND RECORDED RATHER THAN ASSUMED: this fixture carries K and D/ST rows but
    // `lowPred` is `false` on ALL 858 of them, so `sortAvailable`'s K/DST deferral is INERT here.
    // That is why the deferral is proved below on a board built to make it act — a clause asserted
    // against this fixture would pass on a `sortAvailable` that had stopped deferring entirely
    // (NF1.7(a): a mechanism that cannot act is a finding, not a passed test).
    expect(BOARD.filter((p) => p.lowPred === true).length).toBe(0)
  })

  test("an empty document is exactly our order", () => {
    expect(ids(applyDoc(BOARD, EMPTY_DOC))).toEqual(ids(baseOrder(BOARD)))
  })

  test("the base order IS the shared ranking function, K/DST deferral and all", () => {
    // ⭐ E9.61's two-renderers defect, asserted rather than assumed: if this ever stops being
    // `sortAvailable`, the draft optimizer recommends one order and the sheet printed from this
    // screen shows another, with nothing on either saying which is ours.
    expect(ids(baseOrder(BOARD))).toEqual(
      ids(sortAvailable(BOARD, { sortCol: "ovrRank", sortDir: "asc", deferLowPred: true })),
    )
  })

  test("the K/DST deferral genuinely acts, proved on a board where it can", () => {
    // ⚠️ ITS OWN FIXTURE, BECAUSE THE PUBLISHED ONE CANNOT DECIDE IT. The 2026 export carries
    // `lowPred: false` on every row (see the fixture clause above), so the deferral is a no-op
    // there and asserting it against that board would prove nothing. Flagging two high-VOR rows
    // makes the rule's effect the only thing that can move them.
    const flagged = BOARD.map((p, i) => (i < 2 ? { ...p, lowPred: true } : p))
    const order = baseOrder(flagged)
    const lastReal = order.map((p) => p.lowPred === true).lastIndexOf(false)
    const firstLowPred = order.findIndex((p) => p.lowPred === true)
    expect(firstLowPred).toBeGreaterThan(lastReal)
    // ...and they really were at the top before the deferral, or this is satisfied by any order.
    expect(ids(flagged).slice(0, 2)).toEqual(ids(BOARD).slice(0, 2))
  })

  test("every move over a grid round-trips through the stored prefix", () => {
    // ⭐ A GRID, NOT EXAMPLES. The trim keeps the prefix "up to the deepest changed row"; the
    // failure mode is an off-by-one at that boundary, and it only shows for particular (from, to)
    // pairs — which is exactly what hand-picked cases miss.
    const base = ids(baseOrder(BOARD))
    let checked = 0
    for (const from of [0, 1, 5, 40, 199, 300, 857]) {
      for (const to of [0, 1, 4, 39, 200, 301, 857]) {
        if (from === to) continue
        const doc = moveTo(BOARD, EMPTY_DOC, base[from], to)
        const got = ids(applyDoc(BOARD, doc))

        const want = base.slice()
        want.splice(to, 0, want.splice(from, 1)[0])
        expect(got, `move ${from} -> ${to} did not reconstruct`).toEqual(want)

        // ...and it is stored as a PREFIX, never as a copy of the whole board.
        expect(doc.order.length).toBeLessThanOrEqual(Math.max(from, to) + 1)
        checked++
      }
    }
    expect(checked, "the grid was empty — it asserted nothing").toBeGreaterThan(30)
  })

  test("a chain of moves reconstructs, and a big promotion stays small", () => {
    const base = ids(baseOrder(BOARD))
    let doc: BigBoardDoc = EMPTY_DOC
    doc = moveTo(BOARD, doc, base[300], 11)
    // ⭐ THE SIZE PROPERTY THE SHARED ITEM BUDGET DEPENDS ON, stated as it MEASURES rather than as
    // it first read. Promoting #301 to #12 stores 301 ids — not 12 — because every row between the
    // two ends shifts down one; the first draft of this clause claimed 12 and was wrong. What is
    // true, and is what actually bounds the item, is that the prefix runs to the DEEPEST TOUCHED
    // ROW and never to the board's length: it does not grow when the board does, and a user
    // curating their top 50 stores ~50 ids however long the board gets.
    expect(doc.order.length).toBe(301)
    expect(doc.order.length).toBeLessThan(BOARD.length)
    expect(moveTo(BOARD, EMPTY_DOC, base[49], 3).order.length).toBe(50)

    doc = moveTo(BOARD, doc, base[5], 0)
    doc = moveTo(BOARD, doc, base[100], 3)
    const got = ids(applyDoc(BOARD, doc))

    const want = base.slice()
    const move = (id: string, to: number) => {
      const at = want.indexOf(id)
      want.splice(to, 0, want.splice(at, 1)[0])
    }
    move(base[300], 11)
    move(base[5], 0)
    move(base[100], 3)
    expect(got).toEqual(want)
  })

  test("moving a row onto itself, or a row that is not on the board, changes nothing", () => {
    const base = ids(baseOrder(BOARD))
    expect(moveTo(BOARD, EMPTY_DOC, base[7], 7)).toBe(EMPTY_DOC)
    expect(moveTo(BOARD, EMPTY_DOC, "not-a-player", 3)).toBe(EMPTY_DOC)
  })

  test("an out-of-range target is clamped rather than corrupting the order", () => {
    const base = ids(baseOrder(BOARD))
    for (const to of [-5, 99_999]) {
      const got = ids(applyDoc(BOARD, moveTo(BOARD, EMPTY_DOC, base[10], to)))
      expect(got.length).toBe(base.length)
      expect(new Set(got).size).toBe(base.length)
    }
  })

  test("a duplicate id in a stored document renders each player exactly once", () => {
    // A stored duplicate would put one man on the board twice — two rows colliding on their React
    // key, one of which cannot be acted on.
    const base = ids(baseOrder(BOARD))
    const rows = applyDoc(BOARD, { ...EMPTY_DOC, order: [base[4], base[4], base[9]] })
    expect(new Set(ids(rows)).size).toBe(rows.length)
    expect(rows.length).toBe(BOARD.length)
  })

  test("a player who has left the board is dropped, counted, and never silently shortens the rest", () => {
    const base = ids(baseOrder(BOARD))
    const doc: BigBoardDoc = {
      order: [base[3], "retired-player", base[8]],
      tier_breaks: [base[8], "retired-player"],
      tags: { [base[3]]: "target", "retired-player": "avoid" },
      notes: { [base[3]]: "mine", "retired-player": "gone" },
    }
    const rec = reconcile(BOARD, doc)
    expect(rec.droppedOrder).toBe(1)
    expect(rec.droppedBreaks).toBe(1)
    expect(rec.droppedTags).toBe(1)
    // Counted SEPARATELY from tags. Folding them together would make "3 entries were dropped"
    // unattributable, and the banner the user reads is built from these numbers.
    expect(rec.droppedNotes).toBe(1)
    expect(rec.doc.notes).toEqual({ [base[3]]: "mine" })
    expect(rec.doc.order).toEqual([base[3], base[8]])
    // The board itself is unchanged in length — a dropped saved id must not remove a live player.
    expect(applyDoc(BOARD, rec.doc).length).toBe(BOARD.length)
  })

  test("a re-export's new player joins the tail at OUR place, below the curated region", () => {
    // ⭐ THE REASON THE TAIL IS RECOMPUTED RATHER THAN STORED. A saved full copy would freeze the
    // user's board at the vintage they first opened it, and on a board that re-exports weekly that
    // is a wrong answer that looks exactly like a right one.
    //
    // ⚠️ MEASURED, AND THE FIRST DRAFT OF THIS CLAUSE ASSERTED THE WRONG THING. It expected the
    // newcomer at OUR rank; he cannot be, and should not be. The prefix is the user's explicit
    // ranking of rows they have SEEN, so a player published afterwards enters at the top of the
    // UN-CURATED tail — immediately below the region they curated, never inside it and never at the
    // end. Inserting him inside would silently re-rank him above players the user deliberately
    // placed. That is a real product consequence of the prefix and is worth stating rather than
    // discovering: curate the top 200 and a September rookie arrives at 201, not at 4.
    const base = ids(baseOrder(BOARD))
    const doc = moveTo(BOARD, EMPTY_DOC, base[200], 2)
    expect(doc.order.length).toBe(201)

    const newcomer: Player = { ...BOARD[0], id: "brand-new", name: "Brand New", ovrRank: 4 }
    const grown = [...BOARD, newcomer]
    const rows = ids(applyDoc(grown, doc))

    expect(rows, "a newly published player was dropped").toContain("brand-new")
    expect(rows.length).toBe(grown.length)
    // He is below the curated prefix...
    expect(rows.indexOf("brand-new")).toBeGreaterThanOrEqual(doc.order.length)
    // ...and FIRST among the rows the user never touched, because that is where OUR board puts him
    // relative to them. Not merely "somewhere after" — that would also be satisfied by appending.
    const tail = rows.slice(doc.order.length)
    const ourTailOrder = ids(baseOrder(grown)).filter((id) => !doc.order.includes(id))
    expect(tail).toEqual(ourTailOrder)
    expect(tail[0]).toBe("brand-new")
  })
})

test.describe("tiers, tags and the divergence column", () => {
  test("a tier break starts a new tier and nothing else moves", () => {
    const base = baseOrder(BOARD)
    const doc = toggleTierBreak(EMPTY_DOC, base[10].id)
    const tiers = customTiers(applyDoc(BOARD, doc), doc)
    expect(tiers.get(base[9].id)).toBe(1)
    expect(tiers.get(base[10].id)).toBe(2)
    expect(tiers.get(base[11].id)).toBe(2)
    // Toggling it off restores a single tier.
    const off = toggleTierBreak(doc, base[10].id)
    expect(new Set(customTiers(applyDoc(BOARD, off), off).values())).toEqual(new Set([1]))
  })

  test("a break on the very first row is ignored rather than producing an empty tier", () => {
    const base = baseOrder(BOARD)
    const doc = toggleTierBreak(EMPTY_DOC, base[0].id)
    expect(customTiers(applyDoc(BOARD, doc), doc).get(base[0].id)).toBe(1)
  })

  test("clearing a tag removes the key rather than storing a null", () => {
    // An untagged player must cost nothing against the shared item budget.
    const id = BOARD[0].id
    const tagged = setTag(EMPTY_DOC, id, "target")
    expect(tagged.tags).toEqual({ [id]: "target" })
    expect(setTag(tagged, id, null).tags).toEqual({})
  })

  test("the divergence is OUR index minus THEIRS, and is zero for everyone untouched", () => {
    const base = ids(baseOrder(BOARD))
    const doc = moveTo(BOARD, EMPTY_DOC, base[50], 4)
    const d = divergence(BOARD, doc)
    expect(d.get(base[50])).toBe(46) // climbed 46 places
    expect(d.get(base[4])).toBe(-1) // pushed down one
    expect(d.get(base[700])).toBe(0)
    // ⭐ AND IT IS CONSERVATIVE: a pure reorder cannot create or destroy positions.
    expect([...d.values()].reduce((a, b) => a + b, 0)).toBe(0)
  })
})

test.describe("the printed cheat sheet", () => {
  test("groups by the user's own tiers, in their order, and stops at the printed depth", () => {
    const base = baseOrder(BOARD)
    let doc = toggleTierBreak(EMPTY_DOC, base[3].id)
    doc = setTag(doc, base[0].id, "target")
    const sections = cheatSheet(BOARD, doc, 10)
    expect(sections.map((s) => s.tier)).toEqual([1, 2])
    expect(sections[0].rows.map((r) => r.rank)).toEqual([1, 2, 3])
    expect(sections[0].rows[0].tag).toBe("target")
    expect(sections.flatMap((s) => s.rows).length).toBe(10)
  })

  test("the printed depth bounds the PRINT and never the saved order", () => {
    const base = ids(baseOrder(BOARD))
    const doc = moveTo(BOARD, EMPTY_DOC, base[300], 5)
    expect(cheatSheet(BOARD, doc, 20).flatMap((s) => s.rows).length).toBe(20)
    expect(doc.order.length).toBe(301) // the document is untouched by the render depth
  })
})

// ── the browser ─────────────────────────────────────────────────────────────────────────────────

test.describe("notes, and the tiers we can seed", () => {
  test("a note is trimmed, capped, and cleared by emptying it", () => {
    const id = BOARD[0].id
    let doc = setNote(EMPTY_DOC, id, "   sits above his ADP for me   ")
    expect(doc.notes[id]).toBe("sits above his ADP for me")

    doc = setNote(doc, id, "x".repeat(MAX_NOTE_LEN + 50))
    expect(doc.notes[id].length).toBe(MAX_NOTE_LEN)

    // ⚠️ THE KEY IS REMOVED, not set to "". Every note is bytes in the one 400 KB item that holds
    // all of this user's state, and an empty string is bytes that mean nothing.
    doc = setNote(doc, id, "    ")
    expect(id in doc.notes).toBe(false)
  })

  test("our seeded tiers are real groups, in ascending order, and none of them is empty", () => {
    // ⭐ THE ANSWER TO "MY WHOLE SHEET SAYS TIER 1". This is what one click has to produce: a
    // grouping a person can read at a draft table, not a break on every other row.
    const breaks = ourTierBreaks(BOARD, 200)
    expect(breaks.length).toBeGreaterThan(3)
    expect(new Set(breaks).size).toBe(breaks.length)

    const doc: BigBoardDoc = { ...EMPTY_DOC, tier_breaks: breaks }
    const rows = applyDoc(BOARD, doc)
    const tiers = customTiers(rows, doc)

    // Monotone by construction — a tier number that went back down would mean the walk oscillated,
    // which is precisely what the "only when it goes UP" rule in `ourTierBreaks` prevents.
    let last = 0
    const sizes = new Map<number, number>()
    for (const r of rows) {
      const t = tiers.get(r.id)!
      expect(t).toBeGreaterThanOrEqual(last)
      last = t
      sizes.set(t, (sizes.get(t) ?? 0) + 1)
    }
    expect(sizes.size).toBe(breaks.length + 1)
    for (const [, n] of sizes) expect(n).toBeGreaterThan(0)

    // ⚠️ AND THE FIRST ROW IS NEVER A BREAK — a break above row 1 would produce a tier of nobody.
    expect(breaks).not.toContain(rows[0].id)
  })

  test("the seeded tiers describe the pool they are drawn from, and stay readable", () => {
    // ⭐ THE MEASUREMENT THAT DECIDED THE DESIGN. `assignTiers` bounds a tier as a FRACTION of the
    // pool it is handed (4%–15%, by design, so the tier COUNT stays stable whatever n is). Handed
    // the whole board it therefore returns groups of ~40 — the first four rounds in one block, no
    // more use on a cheat sheet than the single tier it replaced. Handed the depth on screen it
    // returns groups a person can read. So the depth is a real parameter, and this is what says so.
    const sizeOf = (depth: number) => {
      const doc: BigBoardDoc = { ...EMPTY_DOC, tier_breaks: ourTierBreaks(BOARD, depth) }
      const rows = applyDoc(BOARD, doc)
      const tiers = customTiers(rows, doc)
      const counts = new Map<number, number>()
      for (const p of rows.slice(0, depth)) {
        const t = tiers.get(p.id)!
        counts.set(t, (counts.get(t) ?? 0) + 1)
      }
      return [...counts.values()]
    }

    const shallow = sizeOf(100)
    const whole = sizeOf(BOARD.length)
    const biggest = (xs: number[]) => Math.max(...xs)
    expect(biggest(shallow)).toBeLessThan(biggest(whole))
    // A draft tier nobody can use is one that swallows a whole round or more. At the depth people
    // actually curate, ours do not.
    expect(biggest(shallow)).toBeLessThanOrEqual(20)
    expect(shallow.length).toBeGreaterThanOrEqual(5)
  })

  test("the seeded tiers are OUR tiers, not this surface's invention", () => {
    // Every break lands where the shared VOR-gap tiering says a group starts, so the user begins
    // from the same structure the Rankings board and the optimizer already show them.
    const breaks = new Set(ourTierBreaks(BOARD, 200))
    const base = baseOrder(BOARD)
    // A break is only ever placed on a row that is genuinely tiered — never on a K/DST or a
    // below-replacement row, which is what `positionTierMap` refuses to tier at all.
    for (const p of base) {
      if (!breaks.has(p.id)) continue
      expect(p.lowPred).not.toBe(true)
      expect(p.vor ?? 0).toBeGreaterThan(0)
    }
  })
})

async function openBigBoard(
  page: Page,
  opts: { customBoards?: "none" | "one" | "atCap"; dropNotes?: boolean } = {},
) {
  const errors = collectPageErrors(page)
  await signIn(page, { groups: ["subscriber"] })
  const mock = await mockApi(page, {
    entitlement: "entitled",
    leagues: "none",
    customBoards: opts.customBoards ?? "none",
    customBoardsDropNotes: opts.dropNotes ?? false,
  })
  await page.goto("/fantasy/big-board")
  await expect(page.getByRole("heading", { name: "My Big Board" })).toBeVisible()
  await expect(page.getByTestId("big-board-row").first()).toBeVisible()
  return { errors, mock }
}

const rowName = (page: Page, i: number) =>
  page.getByTestId("big-board-row").nth(i).getByTestId("big-board-player-name")

/**
 * Drag row `from` onto row `to` with real pointer events.
 *
 * ⚠️ EXPLICIT MOUSE EVENTS, NOT A VALUE SET. The board also offers a rank input, and driving that
 * instead would leave the drag path — the one the feature is named after and the one most likely to
 * break — completely untested. The intermediate `move` is required: the component commits on
 * `pointermove`, so a down/up pair alone would assert that nothing happens.
 */
async function dragRow(page: Page, from: number, to: number) {
  const rows = page.getByTestId("big-board-row")

  // ⚠️ SCROLL BOTH ROWS INTO VIEW BEFORE MEASURING, AND THEN ASSERT THEY REALLY ARE ON SCREEN.
  // `boundingBox()` is VIEWPORT-relative and does NOT scroll — measured on the first cut of this
  // helper, row 6 sat at y=774 in a 720px viewport, so `elementFromPoint` returned null and every
  // pointer event landed on nothing. The board still rendered and the test still ran, so the
  // symptom was "the drag did not reorder" — i.e. a broken HARNESS reporting as a broken FEATURE.
  // The explicit check below turns that into a named failure instead of a plausible one.
  // Centre the SHALLOWER of the two rows: `scrollIntoViewIfNeeded` only scrolls when the element is
  // outside the viewport, so calling it on each row in turn can leave the second one at the very
  // edge — deterministic-looking and half a row off. Centring gives both ends half a viewport of
  // room, which covers any pair this suite drags between.
  await rows.nth(Math.min(from, to)).evaluate((el) => el.scrollIntoView({ block: "center" }))

  const a = await rows.nth(from).getByTestId("big-board-drag-handle").boundingBox()
  const b = await rows.nth(to).boundingBox()
  if (!a || !b) throw new Error("a row had no bounding box — the board did not render")
  const vh = page.viewportSize()?.height ?? 720
  const onScreen = (r: { y: number; height: number }) => r.y >= 0 && r.y + r.height <= vh
  if (!onScreen(a) || !onScreen(b)) {
    throw new Error(
      `rows ${from} and ${to} are not both inside the ${vh}px viewport (handle y=${a.y}, ` +
        `target y=${b.y}) — a drag between them would dispatch onto nothing and read as a ` +
        `feature failure`,
    )
  }

  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2)
  await page.mouse.down()
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 12 })
  await page.mouse.up()
}

test.describe("driving the big board", () => {
  test("it opens on OUR order, and says so", async ({ page }) => {
    const { errors } = await openBigBoard(page)
    await expect(page.getByText("Still exactly our order")).toBeVisible()
    // Every row starts at zero divergence, because nothing has been moved.
    const deltas = await page.getByTestId("big-board-delta").allTextContents()
    expect(deltas.length).toBeGreaterThan(10)
    expect(new Set(deltas.slice(0, 20))).toEqual(new Set(["—"]))
    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("dragging a player up moves him, and the vs-us column says how far", async ({ page }) => {
    const { errors } = await openBigBoard(page)
    const mover = (await rowName(page, 6).textContent())?.trim() ?? ""
    const wasFirst = (await rowName(page, 0).textContent())?.trim() ?? ""
    expect(mover).not.toBe("")
    expect(mover).not.toBe(wasFirst)

    await dragRow(page, 6, 0)

    await expect.poll(async () => (await rowName(page, 0).textContent())?.trim(), {
      message: "the drag did not reorder the board",
    }).toBe(mover)
    // ...and the player he displaced is still on the board, one place lower.
    await expect.poll(async () => (await rowName(page, 1).textContent())?.trim()).toBe(wasFirst)

    const delta = await page.getByTestId("big-board-row").nth(0).getByTestId("big-board-delta").textContent()
    expect(delta?.trim()).toBe("+6")
    // Our own rank stays visible beside it — the whole point of the surface.
    const ours = await page.getByTestId("big-board-row").nth(0).getByTestId("big-board-our-rank").textContent()
    expect(ours?.trim()).toBe("7")

    await expectNoNaN(page)
    expectNoPageErrors(errors)
  })

  test("a reorder is announced as unsaved, then saved, and the round trip survives a reload", async ({
    page,
  }) => {
    // ⭐ THE ASSERTION THE WHOLE FEATURE EXISTS FOR, and the one an echoing mock could fake — see
    // `customBoardResponse` for why the harness stores rather than echoes.
    const { errors } = await openBigBoard(page)
    await expect(page.getByTestId("big-board-save-status")).toContainText("Nothing saved")

    const mover = (await rowName(page, 4).textContent())?.trim() ?? ""
    await dragRow(page, 4, 0)
    await expect(page.getByTestId("big-board-save-status")).toContainText("Unsaved changes")

    await page.getByTestId("big-board-save").click()
    await expect(page.getByTestId("big-board-save-status")).toContainText("✓ Saved")

    await page.reload()
    await expect(page.getByTestId("big-board-row").first()).toBeVisible()
    await expect.poll(async () => (await rowName(page, 0).textContent())?.trim(), {
      message: "the saved board did not survive a reload",
    }).toBe(mover)
    await expect(page.getByTestId("big-board-save-status")).toContainText("Saved board loaded")

    expectNoPageErrors(errors)
  })

  test("a failed read of the saved boards says so, and never says 'nothing saved'", async ({
    page,
  }) => {
    // ⭐ E9.46's class, on the user's own data. "You have nothing saved" is a confident statement
    // about their work that a 503 gives us no standing to make — and it is the one most likely to
    // make someone rebuild a board that is sitting there intact.
    const errors = collectPageErrors(page)
    await signIn(page, { groups: ["subscriber"] })
    await mockApi(page, {
      entitlement: "entitled",
      leagues: "none",
      customBoards: "one",
      fail: ["/fantasy/nfl/custom-boards"],
    })
    await page.goto("/fantasy/big-board")
    await expect(page.getByTestId("big-board-row").first()).toBeVisible()

    const status = page.getByTestId("big-board-save-status")
    await expect(status).toContainText("couldn't load your saved boards")
    await expect(status).not.toContainText("Nothing saved")
    // ...and the board itself still renders, because ours is useful even when theirs is unreadable.
    await expect(page.getByTestId("big-board-row").first()).toBeVisible()
    expectNoPageErrors(errors)
  })

  test("a saved board loads with its tiers and tags, not just its order", async ({ page }) => {
    // The `one` mode's stored board promotes the third row, tags it and puts a tier break on it —
    // so a client that read only `order` would fail this and pass the reorder test above.
    const { errors } = await openBigBoard(page, { customBoards: "one" })
    const top = page.getByTestId("big-board-row").nth(0)
    await expect(top.getByTestId("big-board-target")).toHaveAttribute("data-on", "true")
    await expect(top.getByTestId("big-board-our-rank")).not.toHaveText("1")
    expectNoPageErrors(errors)
  })

  test("a tier break splits the board and a tag marks the row", async ({ page }) => {
    const { errors } = await openBigBoard(page)
    const fourth = page.getByTestId("big-board-row").nth(3)
    await expect(fourth).toHaveAttribute("data-tier", "1")

    await fourth.getByTestId("big-board-tier-break").click()
    await expect(page.getByTestId("big-board-row").nth(3)).toHaveAttribute("data-tier", "2")
    await expect(page.getByTestId("big-board-row").nth(2)).toHaveAttribute("data-tier", "1")

    await fourth.getByTestId("big-board-avoid").click()
    await expect(fourth.getByTestId("big-board-avoid")).toHaveAttribute("data-on", "true")
    // The two tags are mutually exclusive — a player cannot be both.
    await fourth.getByTestId("big-board-target").click()
    await expect(fourth.getByTestId("big-board-avoid")).toHaveAttribute("data-on", "false")
    await expect(fourth.getByTestId("big-board-target")).toHaveAttribute("data-on", "true")

    expectNoPageErrors(errors)
  })

  test("a failed save shows the SERVER's explanation, not a generic one", async ({ page }) => {
    // ⭐ E8.6. The refusal a real user will meet is the shared-item budget, and its whole value is
    // the sentence: it says nothing was changed, which is what makes it recoverable rather than
    // alarming. A client that swallowed `detail` would render "Could not save" and lose that.
    const { errors } = await openBigBoard(page)
    await page.route("**/__e2e-api/fantasy/nfl/custom-boards", async (route) => {
      if (route.request().method() !== "PUT") return route.fallback()
      await route.fulfill({
        status: 413,
        contentType: "application/json",
        body: JSON.stringify({
          detail:
            "This board is too large to save alongside your other saved data. Nothing was changed — delete a custom board you no longer need and try again.",
        }),
      })
    })

    await dragRow(page, 3, 0)
    await page.getByTestId("big-board-save").click()
    await expect(page.getByTestId("big-board-save-status")).toContainText("Nothing was changed")
    await expect(page.getByTestId("big-board-save-status")).not.toContainText("✓ Saved")
    expectNoPageErrors(errors)
  })

  test("the cheat sheet prints the user's decisions and none of our numbers", async ({ page }) => {
    const { errors } = await openBigBoard(page)
    const top = (await rowName(page, 0).textContent())?.trim() ?? ""
    await page.getByTestId("big-board-row").nth(2).getByTestId("big-board-tier-break").click()
    await page.getByTestId("big-board-row").nth(0).getByTestId("big-board-target").click()

    await page.getByTestId("big-board-sheet-toggle").click()
    const sheet = page.getByTestId("big-board-cheat-sheet")
    await expect(sheet).toBeVisible()
    await expect(sheet).toContainText(top)
    await expect(page.getByTestId("big-board-sheet-tier")).toHaveCount(2)

    // ⭐ THE SHEET IS READ AT THE PICK, where a projection beside a ranking the user deliberately
    // overrode is noise that invites second-guessing a decision they already made.
    const text = (await sheet.textContent()) ?? ""
    expect(text).not.toContain("Proj")
    expect(text).not.toContain("VOR")
    expect(text).not.toContain("vs us")
    expectNoPageErrors(errors)
  })

  test("a filter narrows what is shown without renumbering the board", async ({ page }) => {
    // ⚠️ A "#3" meaning "third of the WRs I filtered to" would be a different number wearing the
    // same label — and it is the number the user reads out loud on draft night.
    const { errors } = await openBigBoard(page)
    await page.getByTestId("big-board-pos-filter").and(page.locator('[data-pos="TE"]')).click()
    await expect(page.getByTestId("big-board-row").first()).toBeVisible()

    const firstTeOurRank = await page
      .getByTestId("big-board-row")
      .first()
      .getByTestId("big-board-our-rank")
      .textContent()
    expect(Number(firstTeOurRank)).toBeGreaterThan(1)
    expectNoPageErrors(errors)
  })

  test("the board scrolls inside its own container, never the whole page", async ({ page }) => {
    // ⭐ THE CONTAINER'S `scrollWidth`, NOT THE PAGE'S (NF-C2.1). A page-level check structurally
    // cannot catch a table scrolling inside an `overflow-x-auto` box — the document stays tidy —
    // and a container check alone cannot catch the grid track blowing the page out. Both.
    //
    // ⚠️ AND IT IS ASSERTED AT PHONE WIDTH, WHICH IS THE ONLY PLACE IT CAN FAIL. This spec runs on
    // the desktop project, where the board's 720px minimum fits inside a 1280px viewport — so at
    // that width the page cannot overflow whatever the CSS says, and the first cut of this clause
    // would have passed with `min-w-0` deleted. Narrowing the viewport here is cheaper and more
    // honest than adding the whole spec to the mobile project for one assertion.
    const { errors } = await openBigBoard(page)
    const pageOverflow = async () =>
      page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )
    expect(await pageOverflow(), "the whole page scrolls sideways on desktop").toBeLessThanOrEqual(1)

    await page.setViewportSize({ width: 390, height: 844 })
    await expect(page.getByTestId("big-board-row").first()).toBeVisible()
    expect(await pageOverflow(), "the whole page scrolls sideways on a phone").toBeLessThanOrEqual(1)

    // ...and the board itself DOES have somewhere to scroll, or the clause above is satisfied by a
    // board that simply is not there.
    const scroller = page.getByTestId("big-board-scroller")
    await expect(scroller).toBeVisible()
    const overflow = await scroller.evaluate((el) => el.scrollWidth - el.clientWidth)
    expect(overflow, "the board has no scrolling container of its own").toBeGreaterThan(0)
    expectNoPageErrors(errors)
  })

  test("reset puts our order back and marks the board unsaved", async ({ page }) => {
    const { errors } = await openBigBoard(page)
    const wasFirst = (await rowName(page, 0).textContent())?.trim() ?? ""
    await dragRow(page, 5, 0)
    await expect.poll(async () => (await rowName(page, 0).textContent())?.trim()).not.toBe(wasFirst)

    await page.getByTestId("big-board-reset").click()
    await expect.poll(async () => (await rowName(page, 0).textContent())?.trim()).toBe(wasFirst)
    await expect(page.getByTestId("big-board-save-status")).toContainText("Unsaved changes")
    expectNoPageErrors(errors)
  })

  // ══ the live-surface corrections ═════════════════════════════════════════════════════════════
  // Each of these was WRONG on the deployed page and green in CI, which is the only reason they
  // are worth their runtime: they assert RENDERED output, which is the half a source guard cannot
  // see.

  test("the opening sentence renders with its spaces intact", async ({ page }) => {
    // 🐛 THE DEPLOYED PAGE READ "our 2026board". The season is interpolated inside the string now
    // rather than sitting beside JSX text, and THIS is the assertion that can actually fail for
    // that reason — the source guard can only see how it is written, not how it renders.
    const { errors } = await openBigBoard(page)
    await expect(page.getByText(`Start with our ${SEASON} board for your league`)).toBeVisible()
    const intro = (await page.getByText("Start with our").first().textContent()) ?? ""
    expect(intro).not.toMatch(/\d{4}board/)
    expectNoPageErrors(errors)
  })

  test("every row control says what it does in words, not only as a glyph", async ({ page }) => {
    // ⭐ THE SCISSORS. A star and a no-entry sign can be inferred; "a pair of scissors means start a
    // new tier here" cannot, and a `title` is invisible on the phone where a draft board is read.
    const { errors } = await openBigBoard(page)
    const legend = page.getByTestId("big-board-legend")
    await expect(legend).toBeVisible()
    await expect(legend).toContainText("start a new tier")
    await expect(legend).toContainText("target")
    await expect(legend).toContainText("avoid")
    await expect(legend).toContainText("note")
    expectNoPageErrors(errors)
  })

  test("a note is written, saved, reloaded, and printed on the cheat sheet", async ({ page }) => {
    const { errors } = await openBigBoard(page)
    const row = page.getByTestId("big-board-row").nth(2)
    const who = (await rowName(page, 2).textContent())?.trim() ?? ""

    await row.getByTestId("big-board-note-toggle").click()
    await row.getByTestId("big-board-note-input").fill("handcuff is undrafted in this league")
    await row.getByTestId("big-board-note-done").click()
    await expect(row.getByTestId("big-board-note-text")).toHaveText(
      "handcuff is undrafted in this league",
    )

    await page.getByTestId("big-board-save").click()
    await expect(page.getByTestId("big-board-save-status")).toContainText("Saved")

    // ⭐ A REAL ROUND TRIP. The mock stores what was PUT and serves it back on the next GET, so a
    // client that never sent the notes fails here — which an echoing stub could not tell you.
    await page.reload()
    await expect(page.getByTestId("big-board-row").first()).toBeVisible()
    await expect(
      page.getByTestId("big-board-row").filter({ hasText: who }).first().getByTestId(
        "big-board-note-text",
      ),
    ).toHaveText("handcuff is undrafted in this league")

    // ...and a note is exactly the thing you want ON the sheet you carry to the table.
    await page.getByTestId("big-board-sheet-toggle").click()
    await expect(page.getByTestId("big-board-sheet-note").first()).toHaveText(
      "handcuff is undrafted in this league",
    )
    expectNoPageErrors(errors)
  })

  test("a stored note loads with the board, not only one typed this session", async ({ page }) => {
    // The `one` fixture carries a note. Without this, "notes survive a save" could pass while a
    // stored note never rendered at all.
    const { errors } = await openBigBoard(page, { customBoards: "one" })
    await expect(
      page.getByTestId("big-board-row").nth(0).getByTestId("big-board-note-text"),
    ).toHaveText("my own read on him")
    expectNoPageErrors(errors)
  })

  test("a backend that quietly dropped the notes is reported, not shown as saved", async ({
    page,
  }) => {
    // ⭐ NF-C0 DEPLOY SKEW, WHICH IS GUARANTEED TO HAPPEN AT LEAST ONCE: `frontend/` auto-deploys on
    // merge and the API Lambda ships only via a manual `deploy.sh`, and the request models do not
    // forbid extra fields — so the older backend ACCEPTS `notes`, ignores them, and returns 200.
    // Without the comparison this asserts, the user reads "✓ Saved", reloads, and the note is gone.
    const { errors } = await openBigBoard(page, { dropNotes: true })
    const row = page.getByTestId("big-board-row").nth(1)
    await row.getByTestId("big-board-note-toggle").click()
    await row.getByTestId("big-board-note-input").fill("worth a round earlier than this")
    await row.getByTestId("big-board-note-done").click()

    await page.getByTestId("big-board-save").click()
    const status = page.getByTestId("big-board-save-status")
    await expect(status).toContainText("notes were not")
    // ⚠️ AND IT MUST NOT ALSO CLAIM SUCCESS. "✓ Saved" beside a warning is the message the user
    // reads first, and it is the false half.
    await expect(status).not.toContainText("✓ Saved")
    expectNoPageErrors(errors)
  })

  test("the sheet does not claim a tier the user never drew, and offers ours in one click", async ({
    page,
  }) => {
    // 🐛 REPORTED FROM THE PRINTED SHEET: every player under a single "TIER 1" heading, which reads
    // as a broken tiering rather than as "you have not drawn any".
    const { errors } = await openBigBoard(page)
    await page.getByTestId("big-board-sheet-toggle").click()
    await expect(page.getByTestId("big-board-cheat-sheet")).toBeVisible()
    await expect(page.getByTestId("big-board-cheat-sheet")).not.toContainText("Tier 1")
    await expect(page.getByTestId("big-board-no-tiers")).toBeVisible()

    await page.getByTestId("big-board-sheet-seed-tiers").click()
    // Our tiers are now the user's: several real groups, headed, on their sheet.
    await expect(page.getByTestId("big-board-sheet-tier").first()).toContainText("Tier 1")
    expect(await page.getByTestId("big-board-sheet-tier").count()).toBeGreaterThan(3)
    await expect(page.getByTestId("big-board-no-tiers")).toHaveCount(0)
    expectNoPageErrors(errors)
  })

  test("a player opens in a new tab, so a curated board is never navigated away from", async ({
    page,
  }) => {
    // This board holds unsaved work in component state; a same-tab navigation throws away every
    // drag since the last save.
    const { errors } = await openBigBoard(page)
    const link = rowName(page, 0)
    await expect(link).toHaveAttribute("target", "_blank")
    await expect(link).toHaveAttribute("rel", /noopener/)
    await expect(link).toHaveAttribute("rel", /noreferrer/)
    expectNoPageErrors(errors)
  })

  test("the page chrome is marked so it never reaches the paper", async ({ page }) => {
    // ⚠️ `window.print()` PRINTS THE PAGE. Asserted through the browser's own print media query
    // rather than by reading class names — `matchMedia("print")` cannot be evaluated for layout, so
    // the reachable rendered assertion is that the chrome carries a rule that applies only in print.
    const { errors } = await openBigBoard(page)
    const navHidden = await page.evaluate(() => {
      const nav = document.querySelector("nav")
      let el: HTMLElement | null = nav as HTMLElement | null
      while (el) {
        if (el.className && String(el.className).includes("print:hidden")) return true
        el = el.parentElement
      }
      return false
    })
    expect(navHidden, "the nav bar would print above the cheat sheet").toBe(true)
    expectNoPageErrors(errors)
  })
})
