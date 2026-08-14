// ESPN-PRUNER — the UN-PRUNED ESPN captures, and the contract a capture has to satisfy to count.
//
// ══ WHY THIS MODULE EXISTS SEPARATELY FROM `ESPN_REAL_PASTES` ═══════════════════════════════════
//
// `api-mock.ts`'s `ESPN_REAL_PASTES` are three verbatim captures from real private leagues, and
// they are the right bytes for driving the paste flow. They are the WRONG bytes for testing
// `pruneEspnPayload`, and the reason is the whole point of this story: **all three were already
// pruned before they were committed** — measured, zero occurrences of every field the pruner
// removes. So the pruner has nothing to remove on them, and any assertion that it prunes is
// satisfied by a no-op.
//
// That is the "a post-transform fixture cannot test the transform" shape (NF-C0e): a fixture
// derived from a transform's own OUTPUT can only ever restate it. E9.64b was the first thing in
// the repo to EXECUTE this function, and it ran it on a payload with nothing to prune — which is
// recorded honestly in `e2e/README.md` rather than dressed up as coverage.
//
// ══ WHAT IS AT STAKE ═══════════════════════════════════════════════════════════════════════════
//
// `pruneEspnPayload` is what keeps a real league under the server's 4 MB paste cap. Un-pruned, a
// real drafted response is ~3.3 MB for TEN teams; a 12-team league lands at ~99% of the cap and a
// 14-team league is REFUSED outright — the two commonest sizes on the platform with the largest
// share of fantasy users. And its failure mode is silent: it is wrapped in `catch { return text }`,
// so on any shape it does not expect it hands back the ORIGINAL and the paste simply gets too big.
// From the DOM a corrupted or no-op prune looks exactly like a working one.
//
// ⇒ these captures are the only thing that can tell a working pruner from a silent no-op.

import { readFileSync, existsSync } from "node:fs"
import { join } from "node:path"

/**
 * Same tree as `ESPN_REAL_PASTES`, ON PURPOSE. A capture read across the tree is the one the
 * PYTHON adapter suite is proven against; a second copy under `e2e/fixtures/` would be free to
 * drift from it. See `api-mock.ts`'s note on the same directory.
 */
export const ESPN_RAW_CAPTURE_DIR = join(process.cwd(), "..", "betting_ml", "tests", "fixtures")

/**
 * ⛔ THE SERVER'S CAP, RE-SPELLED — `MAX_PASTE_BYTES` in
 * `app/backend/services/platform_import/espn.py`. It is deliberately not imported (it cannot be,
 * across languages) and deliberately not derived, so this file states the number the browser has
 * to satisfy. The two are pinned to each other by
 * `betting_ml/tests/test_espn_pruner_raw_capture.py::test_the_typescript_suite_states_the_servers_real_cap`,
 * which reads this declaration — so a change to one that is not made to the other goes red rather
 * than leaving the browser tested against a cap the server stopped enforcing.
 */
export const MAX_PASTE_BYTES = 4_000_000

/**
 * The fields the pruner drops, spelled out HERE rather than imported from `fantasy-import.ts`.
 *
 * ⛔ DELIBERATELY A SECOND SPELLING, for the same reason `fantasy-import-espn.spec.ts` keeps its
 * own copy: importing `ESPN_UNREAD_PLAYER_FIELDS` would make every assertion below a restatement
 * of the implementation, and NF-C0e is the standing proof that a test which reads a value back
 * under the key the code wrote can never catch a wrong key. If the two lists disagree, that
 * disagreement IS the finding.
 *
 * `ratings` and `notificationSettings` are removed by the pruner too but are not in that constant
 * (they are deleted by name), so the full removal set is all six.
 */
export const ESPN_REMOVED_FIELDS = [
  "stats",
  "draftRanksByRankType",
  "ownership",
  "outlooks",
  "ratings",
  "notificationSettings",
] as const

/**
 * The three that make up the BULK, and therefore the ones whose presence makes a capture genuinely
 * un-pruned. The pruner's own docstring measures the removed set at 96% of a 3.3 MB response, and
 * it is these per-player blocks that carry it.
 *
 * ⭐ WHY A SUBSET AND NOT ALL SIX: whether `outlooks` / `ratings` / `notificationSettings` appear at
 * all is a fact about what ESPN returns for a given league and view set, not about our pruner. A
 * capture missing one of those is still a valid raw capture. A capture missing ALL THREE bulk
 * drivers is not raw at all — it is a pruned artifact being passed off as one, which is precisely
 * the trap this story exists to close. Per-field counts for all six are reported either way, so a
 * genuine absence is visible rather than silently accepted.
 */
export const ESPN_BULK_DRIVER_FIELDS = ["stats", "draftRanksByRankType", "ownership"] as const

export interface EspnRawCapture {
  /** Stable id, used in test titles and in the operator handoff. */
  id: string
  /** File under `ESPN_RAW_CAPTURE_DIR`. */
  file: string
  /** League size this capture is here to represent. */
  teams: number
  /** Why this particular size is the one worth capturing. */
  why: string
}

/**
 * ⏭️ OPERATOR-SUPPLIED. Nothing in this repo can produce these files.
 *
 * A raw capture requires a real, authenticated, DRAFTED ESPN league — the bulk lives in the roster
 * entries, so an undrafted league has almost none of it. There is no anonymous source: ESPN
 * publishes no developer program, and the only automated path into a private league is replaying a
 * full-account session cookie, which `docs/nf_c0_espn_access_probe.md` refuses on the red line.
 *
 * ⛔ AND IT MUST NOT BE FABRICATED. Re-inflating a pruned capture, or hand-authoring a plausible
 * one, would encode OUR assumption about the very shape under test — the exact defect NF-C0e
 * shipped (a key map that was wrong everywhere at once, and whose test agreed with it). A synthetic
 * would make every assertion below pass while proving nothing about a real payload. Where a
 * synthetic IS legitimate is size and latency, which do not depend on the field names being right;
 * that is what the probe in the spec uses one for, and it is scoped to exactly that claim.
 *
 * HOW TO CAPTURE ONE (per league):
 *   1. Sign in to ESPN in a normal browser, as an account that is IN the league.
 *   2. Open the link the app itself generates — the "Open my league settings" link on the ESPN
 *      import panel, i.e. `build_read_url(league_id, season)`:
 *        https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/<season>
 *          /segments/0/leagues/<league_id>?view=mSettings&view=mTeam&view=mRoster
 *      Use a season the league has already DRAFTED (a completed season is ideal).
 *   3. Select all of the response text and save it VERBATIM to the filename below. ⚠️ Save the raw
 *      response — do not let a JSON viewer/formatter re-serialise it, and do not run it through the
 *      app (the app prunes on the way out, which would recreate the problem).
 *   4. Sanity-check before committing: `grep -c '"stats"' <file>` must be well above zero. If it is
 *      zero the capture was pruned somewhere in transit and is not usable.
 *   5. Commit under `betting_ml/tests/fixtures/`.
 *
 * 🔒 These captures contain league and team names and ESPN player/member ids. They contain NO
 * credential: `espn_s2` is an HTTP cookie and is never echoed into a response body, which is the
 * structural reason this whole paste flow is credential-safe (`espn.py`'s module docstring).
 * `assert_no_credentials` refuses a paste carrying credential material regardless.
 */
export const ESPN_RAW_CAPTURES: readonly EspnRawCapture[] = [
  {
    id: "12-team",
    file: "espn_league_raw_unpruned_12team.json",
    teams: 12,
    why: "un-pruned it lands at ~99% of the 4 MB cap — imports today only by a hair, and only if the pruner works",
  },
  {
    id: "14-team",
    file: "espn_league_raw_unpruned_14team.json",
    teams: 14,
    why: "un-pruned it is REFUSED outright — the pruner is the only reason this size can import at all",
  },
]

export function rawCapturePath(capture: EspnRawCapture): string {
  return join(ESPN_RAW_CAPTURE_DIR, capture.file)
}

export function rawCaptureExists(capture: EspnRawCapture): boolean {
  return existsSync(rawCapturePath(capture))
}

/** Verbatim bytes. Throws if absent — callers gate on `rawCaptureExists` first. */
export function readRawCapture(capture: EspnRawCapture): string {
  return readFileSync(rawCapturePath(capture), "utf8")
}

/** What the SERVER measures: UTF-8 bytes, not JS string length. */
export function payloadBytes(text: string): number {
  return Buffer.byteLength(text, "utf8")
}

/**
 * How many times each removable field appears as a JSON KEY in the raw text.
 *
 * A textual count rather than a structural walk, on purpose: it is independent of where in the
 * document ESPN happens to put a field, so it cannot be fooled by the pruner and the test agreeing
 * on a wrong path. It is what makes "this capture is genuinely un-pruned" and "the pruner actually
 * removed them" separately checkable.
 */
export function removableFieldCounts(text: string): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const field of ESPN_REMOVED_FIELDS) {
    counts[field] = text.split(`"${field}"`).length - 1
  }
  return counts
}

/**
 * The pruner's CONTRACT, applied independently of its source — the same second spelling
 * `fantasy-import-espn.spec.ts` keeps, kept here so both specs state it rather than share an
 * implementation with the code under test.
 */
export function withoutRemovedFields<T>(doc: T): T {
  const copy = JSON.parse(JSON.stringify(doc)) as any
  for (const m of copy.members ?? []) delete m?.notificationSettings
  for (const t of copy.teams ?? []) {
    for (const e of t?.roster?.entries ?? []) {
      const pool = e?.playerPoolEntry
      if (!pool) continue
      delete pool.ratings
      for (const f of ["stats", "draftRanksByRankType", "ownership", "outlooks"]) {
        delete pool.player?.[f]
      }
    }
  }
  return copy
}
