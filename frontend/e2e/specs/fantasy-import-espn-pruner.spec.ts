import { expect, test, type Page } from "@playwright/test"
import { pruneEspnPayload } from "@/lib/fantasy-import"
import { collectPageErrors, mockApi, type ApiMock } from "../support/api-mock"
import { signIn } from "../support/session"
import { expectNoPageErrors } from "../support/assertions"
import {
  ESPN_BULK_DRIVER_FIELDS,
  ESPN_RAW_CAPTURES,
  ESPN_REMOVED_FIELDS,
  MAX_PASTE_BYTES,
  payloadBytes,
  rawCaptureExists,
  rawCapturePath,
  readRawCapture,
  removableFieldCounts,
  withoutRemovedFields,
  type EspnRawCapture,
} from "../support/espn-raw-captures"

/**
 * ESPN-PRUNER — `pruneEspnPayload` against a REAL UN-PRUNED PAYLOAD.
 *
 * ══ THE GAP THIS CLOSES ════════════════════════════════════════════════════════════════════════
 *
 * `pruneEspnPayload` is the single thing keeping a real ESPN league under the server's 4 MB paste
 * cap. Un-pruned, a real drafted response is ~3.3 MB for TEN teams; a 12-team league lands at ~99%
 * of the cap and a 14-team league is REFUSED outright — the two commonest sizes, on the platform
 * with the largest share of fantasy users, sitting at the top of the paid funnel.
 *
 * Nothing had ever tested that it PRUNES. E9.64b was the first thing in the repo to execute the
 * function at all, and it ran on a payload with nothing to prune: all three committed captures were
 * already stripped before being committed (measured — zero occurrences of all six removable
 * fields). So the existing assertion is on the pruner's CONTRACT (posted == pasted minus exactly
 * the unread fields), which is true and useful and is satisfied identically by a function that does
 * nothing at all.
 *
 * That is the NF-C0e shape: a fixture that is the transform's own OUTPUT cannot test the transform.
 * And the failure it hides is silent — `pruneEspnPayload` is wrapped in `catch { return text }`, so
 * on any shape it does not expect it returns the ORIGINAL. From the DOM a no-op prune looks exactly
 * like a working one, right up until the server refuses the paste for size.
 *
 * ══ WHAT IS ASSERTED WHERE, AND WHY THE LINE IS DRAWN THERE ════════════════════════════════════
 *
 * Two claims are in play and they need different evidence:
 *
 *   1. SHAPE + CAP — "it removes the right fields, and the result fits". This depends on our field
 *      names actually matching ESPN's, so it is provable ONLY against a real un-pruned capture. A
 *      synthetic would be built from the same assumption the pruner encodes and would agree with it
 *      no matter how wrong both were — precisely the defect NF-C0e shipped. ⇒ gated on the
 *      operator-supplied captures; SKIPS, loudly, until they land.
 *
 *   2. SIZE + LATENCY — "the control and the pruner survive 3.3 MB". This does NOT depend on the
 *      field names being right, only on the byte volume, so a synthetic of the right SIZE is
 *      legitimate evidence. ⇒ runs today, and is scoped to exactly that claim. It is labelled
 *      everywhere so it can never be read as (1).
 *
 * ⛔ Do not "unblock" (1) by generating a raw payload from a pruned one. That would make every
 * assertion here pass and prove nothing. `espn-raw-captures.ts` documents the capture procedure.
 */

/** ~3.3 MB — the measured size of a real drafted TEN-team response before pruning. */
const REAL_WORLD_PASTE_BYTES = 3_300_000

/** How long the pure function may take on a real-size payload before it is a user-visible stall. */
const PRUNE_BUDGET_MS = 5_000

/** How long the whole paste → prune → POST → render round trip may take before the page has hung.
 *  Well under the 60 s test timeout so a hang FAILS here with a readable message rather than
 *  timing the test out with a generic one. */
const PASTE_SETTLE_MS = 25_000

const REVIEW = /Review what we read/

/** Mirrors `fantasy-import-espn.spec.ts`'s helper. Duplicated rather than shared so that spec's
 *  red-proof cases keep their file untouched. */
async function openEspnPanel(page: Page): Promise<{ errors: string[]; mock: ApiMock }> {
  const errors = collectPageErrors(page)
  await signIn(page, { groups: [] })
  const mock = await mockApi(page, { entitlement: "free", leagues: "none" })
  await page.goto("/fantasy/import")
  await page.getByRole("button", { name: /^ESPN/ }).click()
  await page.getByPlaceholder("Paste your ESPN league ID").fill("998005")
  await page.getByRole("button", { name: /Get my link/ }).click()
  await expect(page.getByRole("link", { name: /Open my league settings/ })).toBeVisible()
  return { errors, mock }
}

/**
 * ⚠️ NOT `fill()` — E9.64b measured Playwright's `fill` exceeding a 60 s timeout on a 207 KB value
 * against this React-controlled `<textarea>`, and this spec pastes payloads 16× larger again.
 * Setting the value through the NATIVE setter and dispatching ONE `input` event is both fast and a
 * closer model of the interaction: a clipboard paste IS a single input event, whereas `fill` is a
 * whole typing protocol. The event is what React's `onChange` listens to.
 */
async function pasteRaw(page: Page, text: string) {
  const box = page.getByPlaceholder(/Paste the text here/)
  await expect(box).toBeVisible()
  await box.evaluate((el, value) => {
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      "value",
    )!.set!
    setter.call(el, value)
    el.dispatchEvent(new Event("input", { bubbles: true }))
  }, text)
  await page.getByRole("button", { name: /Read my league/ }).click()
}

// ══ 1. THE COVERAGE STATE, REPORTED WHETHER OR NOT THE CAPTURES EXIST ═══════════════════════════

test.describe("the un-pruned ESPN capture registry", () => {
  /**
   * ⭐ THIS TEST ALWAYS RUNS, AND IT IS THE ANSWER TO "a skipped test is a vacuous test".
   *
   * The shape assertions below cannot run without an operator-supplied capture, and failing the
   * suite for a missing fixture would just block every unrelated PR. So the honest alternative is
   * to make the gap LOUD and countable: this reports, in the run output and in the report
   * annotations, exactly which claims are proven and which are still owed. A reader of a green run
   * can therefore tell "the pruner is proven on real bytes" from "the pruner is still unproven",
   * which a silent skip cannot.
   */
  test("reports, in the open, which claims are currently proven on real bytes", async () => {
    const lines: string[] = []
    let proven = 0

    for (const capture of ESPN_RAW_CAPTURES) {
      if (!rawCaptureExists(capture)) {
        lines.push(`  ⏭️  ${capture.id}: MISSING — ${capture.file} (operator capture; see espn-raw-captures.ts)`)
        continue
      }
      const counts = removableFieldCounts(readRawCapture(capture))
      const bulk = ESPN_BULK_DRIVER_FIELDS.map((f) => `${f}=${counts[f]}`).join(" ")
      lines.push(`  ✅ ${capture.id}: present, ${bulk}`)
      proven += 1
    }

    const summary =
      `pruneEspnPayload proven on real un-pruned bytes for ${proven}/${ESPN_RAW_CAPTURES.length} ` +
      `declared league sizes\n${lines.join("\n")}`
    console.log(`\n── ESPN pruner coverage ──\n${summary}\n`)
    test.info().annotations.push({ type: "espn-pruner-coverage", description: summary })

    // The registry itself must stay honest: a size we claim to cover has to be declared here, and
    // the sizes that matter are the ones the pruner exists for.
    expect(
      ESPN_RAW_CAPTURES.map((c) => c.teams),
      "the declared capture sizes no longer include the two the pruner exists to rescue",
    ).toEqual(expect.arrayContaining([12, 14]))
  })
})

// ══ 2. THE SHAPE + CAP CLAIMS — REAL BYTES ONLY ════════════════════════════════════════════════

for (const capture of ESPN_RAW_CAPTURES) {
  test.describe(`pruneEspnPayload on a real un-pruned ${capture.id} ESPN league`, () => {
    test.skip(
      () => !rawCaptureExists(capture),
      `⏭️ BLOCKED ON AN OPERATOR CAPTURE: ${capture.file} is not committed. Nothing in this repo ` +
        `can produce it and it must not be fabricated — see e2e/support/espn-raw-captures.ts for ` +
        `the capture procedure. Until it lands, the pruner's DENYLIST and its 4 MB cap behaviour ` +
        `are unproven for a ${capture.teams}-team league.`,
    )

    /**
     * ⭐ THE NON-VACUITY GUARD, AND IT RUNS FIRST ON PURPOSE.
     *
     * Every assertion in this file is satisfied trivially by a payload that has nothing to remove —
     * which is exactly how the three existing captures produced years of apparent coverage for a
     * function nothing had executed. So before anything else: prove this capture is genuinely raw.
     *
     * A capture that has been pruned in transit (by a JSON viewer, by round-tripping it through the
     * app, by an over-helpful export) is byte-plausible and completely useless here, and it fails
     * SILENTLY in the direction of a green suite. This is the one check that cannot be skipped.
     */
    test("the capture is genuinely un-pruned, so the assertions below can fail", () => {
      const raw = readRawCapture(capture)
      const counts = removableFieldCounts(raw)

      // Reported for all six; required for the three that carry the bulk. Whether ESPN returns
      // `outlooks` / `ratings` / `notificationSettings` for a given league and view set is a fact
      // about ESPN, not about our pruner — an absence is visible here rather than silently accepted.
      const report = ESPN_REMOVED_FIELDS.map((f) => `${f}=${counts[f]}`).join(", ")
      test.info().annotations.push({
        type: `raw-capture-${capture.id}`,
        description: `${payloadBytes(raw)} bytes; removable keys: ${report}`,
      })

      for (const field of ESPN_BULK_DRIVER_FIELDS) {
        expect(
          counts[field],
          `${capture.file} contains no "${field}" key, so it is NOT an un-pruned capture — it is a ` +
            `pruned artifact, and every pruner assertion in this file would pass on it while ` +
            `proving nothing. Re-capture it verbatim from the ESPN read URL (see ` +
            `espn-raw-captures.ts) rather than deriving it from a committed fixture. ` +
            `Observed: ${report}`,
        ).toBeGreaterThan(0)
      }
    })

    test("pruning brings the payload under the server's paste cap", () => {
      const raw = readRawCapture(capture)
      const rawSize = payloadBytes(raw)
      const prunedSize = payloadBytes(pruneEspnPayload(raw))

      const pct = (n: number) => `${((n / MAX_PASTE_BYTES) * 100).toFixed(1)}% of the cap`
      test.info().annotations.push({
        type: `cap-${capture.id}`,
        description:
          `raw ${rawSize} B (${pct(rawSize)}) → pruned ${prunedSize} B (${pct(prunedSize)}); ` +
          `raw ${rawSize > MAX_PASTE_BYTES ? "EXCEEDS" : "fits under"} the cap unpruned`,
      })

      // ⭐ THE DoD. Everything else in this file is diagnosis; this is the property the user needs.
      expect(
        prunedSize,
        `a ${capture.teams}-team league does not fit: ${prunedSize} B against a ${MAX_PASTE_BYTES} B ` +
          `cap. ${capture.why}`,
      ).toBeLessThan(MAX_PASTE_BYTES)

      // ⭐ AND THE PRUNING IS LOAD-BEARING, not incidental whitespace. The docstring measures the
      // removed set at ~96% of a real response; requiring only a halving leaves wide margin while
      // still going red on a pruner that silently degraded to a JSON round trip. This is the
      // assertion the existing spec explicitly could NOT make ("the ~37% it does shrink the payload
      // by is WHITESPACE"), and having a raw capture is the entire reason it is available here.
      expect(
        prunedSize,
        `pruning removed almost nothing (${rawSize} B → ${prunedSize} B). On a raw capture the ` +
          `removable blocks are the overwhelming majority of the payload, so a result this close ` +
          `to the input means the denylist did not match — or the catch swallowed a throw and ` +
          `returned the original.`,
      ).toBeLessThan(rawSize / 2)
    })

    test("it removes exactly the unread fields, and nothing else", () => {
      const raw = readRawCapture(capture)
      const pruned = pruneEspnPayload(raw)

      // ⭐ THE SILENT-CATCH PATH, CAUGHT. `pruneEspnPayload` returns its INPUT verbatim on anything
      // unexpected, which is the right behaviour (the server owns validation) and the reason a bug
      // here is invisible. On a raw capture the returned text MUST differ from the input; identity
      // means the catch fired, or the walk found nothing to walk.
      expect(
        pruned,
        `the pruner returned its input unchanged. On a capture that carries removable blocks this ` +
          `can only mean the JSON.parse threw and the catch handed the original back, or the ` +
          `document shape no longer matches the paths the pruner walks.`,
      ).not.toBe(raw)

      // Nothing removable survives...
      const after = removableFieldCounts(pruned)
      for (const field of ESPN_REMOVED_FIELDS) {
        expect(after[field], `"${field}" survived pruning`).toBe(0)
      }

      // ...and nothing else was touched. Compared against a SECOND SPELLING of the contract rather
      // than against the pruner's own constant — importing `ESPN_UNREAD_PLAYER_FIELDS` would make
      // this a restatement of the implementation, which is how NF-C0e's wrong key map survived its
      // own test suite. If the two spellings disagree, that disagreement is the finding.
      expect(JSON.parse(pruned)).toEqual(withoutRemovedFields(JSON.parse(raw)))
    })

    test("everything the import reads survives the rewrite", () => {
      const raw = JSON.parse(readRawCapture(capture))
      const pruned = JSON.parse(pruneEspnPayload(readRawCapture(capture)))

      // The server resolves the league from these two, so losing either turns a good paste into an
      // unrecognisable one — the failure mode a size-only assertion would sail straight past.
      expect(pruned.id, "the league id did not survive pruning").toBe(raw.id)
      expect(pruned.seasonId, "the season did not survive pruning").toBe(raw.seasonId)
      expect(pruned.settings, "league settings did not survive pruning").toEqual(raw.settings)

      // The roster is what makes the team picker and the roster chips reachable; the pruner walks
      // straight through it, so it is the structure most at risk from a bad path.
      expect(pruned.teams?.length, "the team list did not survive pruning").toBe(raw.teams?.length)
      const rawEntries = (raw.teams ?? []).map((t: any) => t?.roster?.entries?.length ?? 0)
      const prunedEntries = (pruned.teams ?? []).map((t: any) => t?.roster?.entries?.length ?? 0)
      expect(prunedEntries, "roster entries were dropped").toEqual(rawEntries)

      // And the player identity the board matches on, which lives one level under the field the
      // pruner deletes from — a path off by one level would take the whole player with it.
      const firstPlayer = (doc: any) =>
        doc?.teams?.[0]?.roster?.entries?.[0]?.playerPoolEntry?.player
      if (firstPlayer(raw)) {
        expect(firstPlayer(pruned)?.id, "player identity was lost").toBe(firstPlayer(raw).id)
        expect(firstPlayer(pruned)?.fullName, "player name was lost").toBe(
          firstPlayer(raw).fullName,
        )
      }
    })

    test("pasting the raw payload sends the server something it will accept", async ({ page }) => {
      test.setTimeout(90_000)
      const raw = readRawCapture(capture)
      const { mock, errors } = await openEspnPanel(page)

      await pasteRaw(page, raw)

      // The harness records what left the browser BEFORE it decides how to answer, so this asserts
      // on the real POST body regardless of whether a preview fixture exists for this league.
      await expect
        .poll(() => mock.espnPastes.length, {
          timeout: PASTE_SETTLE_MS,
          message:
            `a ${payloadBytes(raw)} B paste never reached the API within ${PASTE_SETTLE_MS} ms — ` +
            `the control or the prune hung at real size`,
        })
        .toBe(1)

      const [sent] = mock.espnPastes
      expect(
        sent.postedBytes,
        `the browser posted ${sent.postedBytes} B against a ${MAX_PASTE_BYTES} B server cap — the ` +
          `server would refuse this paste for size`,
      ).toBeLessThan(MAX_PASTE_BYTES)

      expectNoPageErrors(errors)
    })
  })
}

// ══ 3. THE SIZE + LATENCY CLAIM — LEGITIMATELY SYNTHETIC ═══════════════════════════════════════

/**
 * A document of REAL SIZE and roughly real shape.
 *
 * ⚠️⚠️ THIS PROVES NOTHING ABOUT THE DENYLIST, and must never be used to. It is built from the same
 * assumption about ESPN's field names that the pruner encodes, so it would agree with a wrong
 * pruner exactly as readily as with a right one — the NF-C0e defect, reproduced on demand. Its ONLY
 * job is to put ~3.3 MB through the control and the function, and byte volume does not depend on
 * the field names being right.
 *
 * The largest payload ever put through this control before this spec was 207 KB, 16× smaller than a
 * real un-pruned response, so this is genuinely unmeasured territory rather than a formality.
 */
function syntheticPayloadOfSize(targetBytes: number): string {
  // A per-player block shaped like the bulk ESPN actually ships: a stat line per scoring period.
  const statBlock = (playerId: number) =>
    Array.from({ length: 24 }, (_, i) => ({
      id: `${playerId}-${i}`,
      scoringPeriodId: i,
      seasonId: 2025,
      statSourceId: i % 2,
      statSplitTypeId: 1,
      appliedTotal: 12.34,
      stats: Object.fromEntries(Array.from({ length: 40 }, (_, k) => [String(k), k * 1.5])),
    }))

  const entry = (playerId: number) => ({
    playerId,
    lineupSlotId: playerId % 20,
    acquisitionType: "DRAFT",
    playerPoolEntry: {
      id: playerId,
      ratings: { "0": { positionalRanking: 12, totalRanking: 44, totalRating: 9.1 } },
      player: {
        id: playerId,
        fullName: `Synthetic Player ${playerId}`,
        defaultPositionId: 2,
        eligibleSlots: [2, 3, 20, 21],
        stats: statBlock(playerId),
        draftRanksByRankType: { STANDARD: { rank: 40, auctionValue: 3 }, PPR: { rank: 38 } },
        ownership: { percentOwned: 55.5, percentChange: 0.4, percentStarted: 40.1 },
        outlooks: { outlooksByWeek: Object.fromEntries(Array.from({ length: 18 }, (_, w) => [String(w), "x".repeat(200)])) },
      },
    },
  })

  let playerId = 1
  const doc: any = {
    id: 999999,
    seasonId: 2025,
    gameId: 1,
    segmentId: 0,
    scoringPeriodId: 18,
    settings: { name: "Synthetic size probe", size: 14 },
    members: Array.from({ length: 14 }, (_, i) => ({
      id: `m${i}`,
      displayName: `member${i}`,
      notificationSettings: Array.from({ length: 30 }, (_, n) => ({
        id: `n${n}`,
        type: "TRADE_OFFER",
        enabled: true,
      })),
    })),
    teams: Array.from({ length: 14 }, (_, t) => ({
      id: t + 1,
      name: `Team ${t + 1}`,
      roster: { entries: [] as any[] },
    })),
  }

  // Grow round-robin until the serialised document reaches the target, so the size is MEASURED
  // rather than assumed from a per-player estimate that would drift with the block above.
  let team = 0
  while (Buffer.byteLength(JSON.stringify(doc), "utf8") < targetBytes) {
    doc.teams[team % doc.teams.length].roster.entries.push(entry(playerId++))
    team += 1
  }
  return JSON.stringify(doc)
}

test.describe("real-size paste behaviour (SIZE ONLY — see the header)", () => {
  test("the pruner survives a real-size payload without stalling", () => {
    const payload = syntheticPayloadOfSize(REAL_WORLD_PASTE_BYTES)
    expect(payloadBytes(payload)).toBeGreaterThanOrEqual(REAL_WORLD_PASTE_BYTES)

    const started = Date.now()
    const pruned = pruneEspnPayload(payload)
    const elapsed = Date.now() - started

    const measurement = `${payloadBytes(payload)} B → ${payloadBytes(pruned)} B in ${elapsed} ms`
    console.log(`\n── ESPN pruner, real-size latency ──\n  ${measurement}\n`)
    test.info().annotations.push({ type: "prune-latency", description: measurement })
    expect(
      elapsed,
      `pruning a ${payloadBytes(payload)} B payload took ${elapsed} ms — long enough to read as a ` +
        `frozen tab on the click that submits a paste`,
    ).toBeLessThan(PRUNE_BUDGET_MS)

    // ⭐ A SELF-CONSISTENCY REGRESSION GUARD, AND EXPLICITLY NOT A CORRECTNESS CLAIM.
    //
    // This synthetic is built from the SAME belief about ESPN's shape that the pruner encodes, so
    // it can never tell you that belief is right — a pruner wrong about real ESPN in exactly the
    // way this generator is wrong would sail through. That is the whole reason the real captures
    // above are an operator dependency and not something this file quietly works around.
    //
    // What it CAN catch, and what nothing else catches until those captures land, is the walk
    // BREAKING relative to the shape we believe: a renamed key, a path that goes one level wrong,
    // a refactor that drops a loop, or the catch firing and handing the original straight back.
    // Without a ratio here that class is invisible — pruning `members` alone still makes the
    // output "smaller", so a mere `< input` assertion passes with the entire player walk dead.
    const removedFraction = 1 - payloadBytes(pruned) / payloadBytes(payload)
    expect(
      removedFraction,
      `pruning removed only ${(removedFraction * 100).toFixed(1)}% of a payload that is mostly ` +
        `removable blocks. Either the walk no longer reaches them (a renamed key or a wrong path — ` +
        `the NF-C0e class), or the parse threw and the catch returned the input unchanged.`,
    ).toBeGreaterThan(0.5)
  })

  test("a real-size paste does not hang the import control", async ({ page }) => {
    test.setTimeout(90_000)
    const payload = syntheticPayloadOfSize(REAL_WORLD_PASTE_BYTES)
    const { mock, errors } = await openEspnPanel(page)

    const started = Date.now()
    await pasteRaw(page, payload)

    // ⭐ THE QUESTION THIS TEST EXISTS FOR. E9.64b measured Playwright's `fill` timing out at 60 s
    // on 207 KB; nothing had ever put 16× that through this control. A hang here would be a real
    // user pressing a button and watching a dead page, on the highest-value import path we have.
    await expect
      .poll(() => mock.espnPastes.length, {
        timeout: PASTE_SETTLE_MS,
        message: `a ${payloadBytes(payload)} B paste never reached the API within ${PASTE_SETTLE_MS} ms`,
      })
      .toBe(1)

    const elapsed = Date.now() - started
    const measurement =
      `${payloadBytes(payload)} B pasted into the real <textarea>, pruned, and POSTed as ` +
      `${mock.espnPastes[0].postedBytes} B in ${elapsed} ms`
    console.log(`\n── ESPN pruner, real-size paste round trip ──\n  ${measurement}\n`)
    test.info().annotations.push({ type: "paste-round-trip", description: measurement })

    // The synthetic league is not one the harness knows, so the server's answer is the honest 422.
    // What matters is that the page SETTLED into a state the user can act on rather than hanging,
    // and that the control is still usable afterwards.
    await expect(
      page.getByRole("button", { name: /Read my league/ }),
      "the import control never came back after a real-size paste",
    ).toBeEnabled({ timeout: PASTE_SETTLE_MS })
    await expect(page.getByRole("heading", { name: REVIEW })).toHaveCount(0)

    expectNoPageErrors(errors)
  })
})
