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
  removableFieldCounts,
  resolveCapture,
  withoutRemovedFields,
} from "../support/espn-raw-captures"

/**
 * ESPN-PRUNER — `pruneEspnPayload` against a REAL UN-PRUNED PAYLOAD.
 *
 * ══ THE GAP THIS CLOSES ════════════════════════════════════════════════════════════════════════
 *
 * `pruneEspnPayload` rewrites every ESPN paste on its way to the server, on the platform with the
 * largest share of fantasy users, at the top of the paid funnel.
 *
 * ⚠️ ITS STATED JUSTIFICATION DID NOT SURVIVE MEASUREMENT — see `fantasy-import.ts`. The claim was
 * "3.3 MB un-pruned ⇒ a 12-team league at ~99% of the 4 MB cap and a 14-team REFUSED". The real
 * captured response is 834 KB (20.9% of the cap) → 131 KB pruned: a 6.4× reduction, with no
 * measured league size near the cap. That makes this a payload reduction rather than a
 * load-bearing gate — still worth keeping, and still worth testing, but not for the reason
 * recorded. (The capture is a COMPLETED season; an in-season response is unmeasured.)
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
 * Two claims are in play, they need different evidence, and the whole design here is keeping them
 * apart:
 *
 *   1. SHAPE — "it removes the RIGHT fields". This depends on our field names actually matching
 *      ESPN's, so it is provable ONLY against a real un-pruned capture. Anything we generate is
 *      built from the same assumption the pruner encodes and would agree with it no matter how
 *      wrong both were — precisely the defect NF-C0e shipped. ⇒ needs a real capture; SKIPS,
 *      loudly, until one lands. **One real capture carries this for every league size**, because
 *      it is a claim about ESPN's field names, not about league size.
 *
 *   2. SIZE — "a payload this big prunes to something that fits, and the control survives it".
 *      This does NOT depend on the field names being right, only on byte volume. So it can be
 *      answered two ways that are both honest, and are labelled distinctly wherever they appear:
 *        · SIZE-EXTENDED — real teams REPLICATED out of the real capture to reach a league size we
 *          have no DRAFTED league for (the captured league is 10-team). Every byte is genuine ESPN
 *          output. Adds real size evidence, and ZERO independent shape evidence.
 *        · SYNTHETIC — a generated document at the STRESS size below, used only for latency and for
 *          catching the walk BREAKING. Never for a claim about ESPN.
 *
 * ⛔ Do not "unblock" (1) by generating a raw payload, or by promoting a size-extended one. Two
 * copies of one payload are one payload. `espn-raw-captures.ts` documents the capture procedure,
 * and notes that a PUBLIC ESPN league is readable with no credential at all if a genuinely
 * independent second payload is wanted.
 */

/**
 * The STRESS size for the latency probe: 3.3 MB.
 *
 * ⚠️ THIS IS NOT A MEASUREMENT, and it used to be labelled as one ("the measured size of a real
 * drafted ten-team response"). The real captured response is 834 KB; 3.3 MB is the figure the
 * pruner's docstring claimed, and measuring it is what disproved it. It is KEPT as the probe size
 * deliberately — it is ~4× the largest real payload we have seen, so it bounds the control's
 * behaviour well beyond anything a user is known to produce, and it is the size an in-season
 * response would have to reach for the original claim to have been right.
 */
const STRESS_PASTE_BYTES = 3_300_000

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
    let captured = 0
    let extended = 0

    for (const capture of ESPN_RAW_CAPTURES) {
      const resolved = resolveCapture(capture)
      if (!resolved) {
        lines.push(
          `  ⏭️  ${capture.id}: UNAVAILABLE — ${capture.file} (see espn-raw-captures.ts)`,
        )
        continue
      }
      const counts = removableFieldCounts(resolved.text)
      const bulk = ESPN_BULK_DRIVER_FIELDS.map((f) => `${f}=${counts[f]}`).join(" ")
      lines.push(`  ✅ ${capture.id}: ${resolved.provenance}, ${bulk}`)
      resolved.isIndependentEvidence ? (captured += 1) : (extended += 1)
    }

    // ⭐ THE TWO COUNTS ARE REPORTED SEPARATELY, AND THAT SEPARATION IS THE HONESTY.
    // A size-extended payload replicates real teams out of a real capture, so it answers the SIZE
    // question at that league size and adds ZERO independent evidence about ESPN's field shape.
    // Collapsing the two into one "N/2 proven" would launder the second into the first.
    const summary =
      `pruneEspnPayload — SHAPE proven on ${captured} independently-captured real payload(s); ` +
      `SIZE additionally covered at ${extended} size-extended league size(s)\n${lines.join("\n")}`
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
      () => resolveCapture(capture) === null,
      `⏭️ BLOCKED ON AN OPERATOR CAPTURE: no real un-pruned ESPN payload is committed, so nothing ` +
        `can be resolved for a ${capture.teams}-team league. Nothing in this repo can produce one ` +
        `and it must not be fabricated — see e2e/support/espn-raw-captures.ts. Until it lands, the ` +
        `pruner's DENYLIST and its 4 MB cap behaviour are unproven at every league size.`,
    )

    /** The bytes under test, plus an honest label. ⚠️ Read once per test rather than hoisted: the
     *  file can land between runs, and a module-scope read would pin the skip decision to whatever
     *  was on disk when the file was first imported. */
    const bytes = () => {
      const resolved = resolveCapture(capture)!
      return resolved
    }

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
      const { text: raw, provenance } = bytes()
      const counts = removableFieldCounts(raw)
      test.info().annotations.push({ type: `provenance-${capture.id}`, description: provenance })

      // Reported for all six; required for the three that carry the bulk. Whether ESPN returns
      // `outlooks` / `ratings` / `notificationSettings` for a given league and view set is a fact
      // about ESPN, not about our pruner — an absence is visible here rather than silently accepted.
      const report = ESPN_REMOVED_FIELDS.map((f) => `${f}=${counts[f]}`).join(", ")
      test.info().annotations.push({
        type: `raw-capture-${capture.id}`,
        description: `${payloadBytes(raw)} bytes; removable keys: ${report}`,
      })

      // ⚠️ ORDER IS LOAD-BEARING — DIAGNOSE THE UNDRAFTED CASE FIRST. An UNDRAFTED league and a
      // PRUNED artifact both present as "no bulk fields" and need OPPOSITE fixes (re-capture a
      // different SEASON vs re-capture without the transform). The first real capture attempt was
      // exactly this: a pre-draft league, 48 KB, `stats` occurring zero times, every team with 0
      // roster entries — and reporting that as "a pruned artifact" sends the reader at the wrong
      // fix. A suggested cause is diagnostic anchoring (INC-40); it must be right or absent.
      const doc = JSON.parse(raw)
      const entryCounts = (doc.teams ?? []).map(
        (t: any) => (t?.roster?.entries ?? []).length as number,
      )
      expect(
        entryCounts.some((n: number) => n > 0),
        `the ${capture.id} payload (${provenance}) has ${entryCounts.length} teams and NO roster ` +
          `entries on any of them (drafted=${doc?.draftDetail?.drafted}) — a faithful capture of a ` +
          `league that has NOT DRAFTED. The removable bulk lives in the roster entries, so a ` +
          `pre-draft league carries none of it. Re-capture a season the league has already drafted.`,
      ).toBe(true)

      for (const field of ESPN_BULK_DRIVER_FIELDS) {
        expect(
          counts[field],
          `the ${capture.id} payload (${provenance}) has populated rosters but no "${field}" key, ` +
            `so the bulk was stripped in transit — it is a pruned artifact, and every pruner ` +
            `assertion in this file would pass on it while proving nothing. Re-capture verbatim ` +
            `from the ESPN read URL (see espn-raw-captures.ts) without routing it through the app ` +
            `or a JSON viewer. Observed: ${report}`,
        ).toBeGreaterThan(0)
      }

      // A SIZED leg has to be the size it claims, whether captured or extended — a 14-team result
      // read off a 12-team document would be the quietest possible way for this leg to say nothing.
      // The shape-carrying entry declares no size (see `EspnRawCapture.teams`).
      if (capture.teams != null) {
        expect(
          entryCounts.length,
          `the ${capture.id} payload carries the wrong number of teams`,
        ).toBe(capture.teams)
      }
    })

    test("pruning brings the payload under the server's paste cap", () => {
      const { text: raw, provenance } = bytes()
      const rawSize = payloadBytes(raw)
      const prunedSize = payloadBytes(pruneEspnPayload(raw))

      // ⭐ THE INHERITED CLAIM, TURNED INTO A MEASUREMENT. "12-team ≈99% of the cap, 14-team
      // REFUSED" has been quoted in three places since NF-C0e and was itself EXTRAPOLATED from one
      // 10-team measurement — nobody had ever weighed a payload at either size. It is REPORTED here
      // rather than asserted: a real capture that disagrees is a docstring to correct, not a test
      // to fail, and failing on it would be reverse-engineering the bar from the answer.
      const pct = (n: number) => `${((n / MAX_PASTE_BYTES) * 100).toFixed(1)}% of the cap`
      const measurement =
        `${capture.id} (${provenance}): raw ${rawSize} B (${pct(rawSize)}) → pruned ${prunedSize} B ` +
        `(${pct(prunedSize)}); un-pruned it ${rawSize > MAX_PASTE_BYTES ? "EXCEEDS the cap (would be REFUSED)" : "fits under the cap"}`
      console.log(`\n── ESPN pruner, cap headroom ──\n  ${measurement}\n`)
      test.info().annotations.push({ type: `cap-${capture.id}`, description: measurement })

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
      const { text: raw } = bytes()
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
      const { text } = bytes()
      const raw = JSON.parse(text)
      const pruned = JSON.parse(pruneEspnPayload(text))

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

    test("pasting the raw payload posts a body that fits under the cap", async ({ page }) => {
      test.setTimeout(90_000)
      const { text: raw } = bytes()
      const { mock, errors } = await openEspnPanel(page)

      await pasteRaw(page, raw)

      // ⚠️ SCOPED TO WHAT LEFT THE BROWSER, deliberately — this does NOT assert the review screen
      // renders. The harness resolves a preview by the paste's own `(id, seasonId)` and these
      // captures are not in `ESPN_REAL_PASTES`, so the mock answers its honest 422. Rendering the
      // review for them would mean generating preview fixtures from the shipping adapter
      // (`build-import-previews.py`), which cannot be done until the captures land. The size claim
      // is the one that matters here and it is fully reachable: the harness records what was POSTed
      // BEFORE it decides how to answer.
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
    const payload = syntheticPayloadOfSize(STRESS_PASTE_BYTES)
    expect(payloadBytes(payload)).toBeGreaterThanOrEqual(STRESS_PASTE_BYTES)

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
    const payload = syntheticPayloadOfSize(STRESS_PASTE_BYTES)
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
