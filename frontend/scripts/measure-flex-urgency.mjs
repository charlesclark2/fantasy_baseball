#!/usr/bin/env node --experimental-strip-types
// measure-flex-urgency.mjs — how often does the FLEX-POOL urgency rule change the advice?
//
// ⭐ WHY THIS EXISTS. The operator's fourth NF-C2.1 note was that the draft kept pushing TEs into
// the FLEX seat. It does, and the mechanism is one line in `recommend`: the flex need bonus was
// `NEED_W_FLEX x (the gap to the next player at the SAME position)`, and TE — the thinnest position
// on the board — has structurally the steepest within-position cliffs. Changing that is a change to
// the SHARED engine, so the live Draft Optimizer moves with it. "It looked wrong in one mock" is not
// enough to re-order a paid product's advice; a measured flip rate on the SERVED board is.
//
// ⛔ NOT A GUARD, and deliberately not a spec. It reads a 240 KB artifact that is not in the repo, so
// as a test it could only ever skip in CI — a permanently-skipped guard is the vacuous kind this repo
// keeps finding. It is an INSTRUMENT: re-runnable on demand, and it prints the numbers quoted in
// `draft-optimizer.ts`'s comment so a future reader can check them rather than trust them.
//
// RUN (laptop):
//   aws s3 cp s3://credence-prod-s3-api-cache/fantasy/nfl/2026/board_full_ppr_12.json /tmp/board.json --region us-east-1
//   aws s3 cp s3://credence-prod-s3-api-cache/fantasy/nfl/2026/manifest.json /tmp/manifest.json --region us-east-1
//   cd frontend && node --experimental-strip-types scripts/measure-flex-urgency.mjs /tmp/board.json /tmp/manifest.json full_ppr
//
// HOW THE COUNTERFACTUAL IS BUILT. `recommend` returns `score`, `seatValue`, `needBonus`,
// `positionalDropoff` and `needLevel` per candidate, and the old rule is a pure function of those
// plus the player's published `vor`:
//
//     old_need_bonus = best-at-his-position ? NEED_W[level] * positionalDropoff : 0
//     old_score      = score - seatValue + vor - needBonus + old_need_bonus
//
// so the pre-change ordering is reconstructible EXACTLY from the post-change output — no second
// engine, no forked copy that can drift. Only level-1 (FLEX-only) candidates differ; level 0 and 2
// reconstruct byte-identically, which is itself the control this script asserts before reporting.
//
// TWO CHANGES LANDED TOGETHER and they are reported separately, because they are not the same size:
//   BASE  — a flex-only candidate is scored against the FLEX SEAT's replacement, not his own
//           position's. This is the one that does the work.
//   BONUS — the flex need bonus multiplies the gap over the FLEX POOL, not the within-position gap.
//           Principled, and measured near-inert once BASE is in.
//
// ⚠️ PAIRED, AND RUN BOTH WAYS. My picks change the draft, so the states reached under one rule are
// not the states reached under the other. Driving with the new rule answers "at the states the new
// tool reaches, how often would the old have disagreed"; driving with the old rule answers the
// mirror. A one-directional read would be a selection effect, so both are printed.

import fs from "node:fs"
import { recommend, openStarterSlots, rosterRequirements, NEED_W_FLEX } from "../lib/draft-optimizer.ts"

const [boardPath, manifestPath, configName = "full_ppr", nTeamsArg = "12"] = process.argv.slice(2)
if (!boardPath || !manifestPath) {
  console.error("usage: measure-flex-urgency.mjs <board.json> <manifest.json> [configName] [nTeams]")
  process.exit(2)
}
const N_TEAMS = Number(nTeamsArg)
const SEEDS = 200

const board = JSON.parse(fs.readFileSync(boardPath, "utf8"))
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"))
const config = manifest.configs.find((c) => c.name === configName)
if (!config) throw new Error(`config ${configName} not in the manifest`)
const ROUNDS = config.roster.reduce((n, s) => n + s.count, 0)

// ── a deterministic ADP room, so the states are the ones a real draft reaches ───────────────────
// Same shape as the mock-draft CPU (ADP order + a widening gaussian), re-implemented here rather
// than imported so this instrument depends on ONE module — the one under measurement.
function makeRng(seed) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
const gauss = (rng) => {
  const u = Math.max(rng(), 1e-9)
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rng())
}

const adpOrder = [...board]
  .filter((p) => p.vor != null)
  .sort((a, b) => (a.adp ?? 1e6) - (b.adp ?? 1e6) || a.ovrRank - b.ovrRank)

/** Positions a team with these players can still roster at all (starters, flex or bench). */
function acceptable(myPositions) {
  const req = rosterRequirements(config.roster)
  const open = openStarterSlots(myPositions, req)
  const ok = new Set()
  for (const [pos, n] of Object.entries(open.dedicated)) if (n > 0) ok.add(pos)
  for (const s of open.flex) s.forEach((e) => ok.add(e))
  const benchLeft = ROUNDS - myPositions.length - (Object.values(open.dedicated).reduce((a, n) => a + n, 0) + open.flex.length)
  if (benchLeft > 0) for (const s of config.roster) s.eligible.forEach((e) => ok.add(e))
  return ok
}

function cpuPick(rng, drafted, myPositions, round) {
  const ok = acceptable(myPositions)
  const sigma = 6 + 3.2 * round
  const pool = []
  for (const p of adpOrder) {
    if (drafted.has(p.id) || !ok.has(p.pos)) continue
    pool.push(p)
    if (pool.length >= 40) break
  }
  if (!pool.length) return null
  let best = null
  let bestKey = Infinity
  pool.forEach((p, i) => {
    const key = i + gauss(rng) * (sigma / 8)
    if (key < bestKey) {
      bestKey = key
      best = p
    }
  })
  return best
}

// ── the counterfactual ─────────────────────────────────────────────────────────────────────────
const NEED_W = { 0: 0, 1: NEED_W_FLEX, 2: 1.0 }

/** Rebuild a PRE-change ordering from the post-change recommendations.
 *  `revert` picks which half to undo: "both" (the full counterfactual), "base" or "bonus". */
function oldOrder(recs, revert = "both") {
  const bestAtPos = new Map()
  for (const r of recs) {
    const cur = bestAtPos.get(r.player.pos)
    if (!cur || (r.player.pts ?? 0) > (cur.player.pts ?? 0)) bestAtPos.set(r.player.pos, r)
  }
  const rescored = recs.map((r) => {
    const isBest = bestAtPos.get(r.player.pos) === r
    const oldBonus = isBest ? NEED_W[r.needLevel] * r.positionalDropoff : 0
    let s = r.score
    if (revert === "both" || revert === "base") s += (r.player.vor ?? 0) - r.seatValue
    if (revert === "both" || revert === "bonus") s += oldBonus - r.needBonus
    return { ...r, oldScore: s }
  })
  rescored.sort((a, b) => {
    if (a.mustFill !== b.mustFill) return a.mustFill ? -1 : 1
    if (a.deferred !== b.deferred) return a.deferred ? 1 : -1
    return b.oldScore - a.oldScore
  })
  return rescored
}

/** ⭐ THE CONTROL. Level 0 and level 2 candidates are untouched by the change, so their
 *  reconstruction must be exact. If this ever fires, the counterfactual is measuring the
 *  reconstruction's own error rather than the rule. */
function assertReconstructionIsExact(recs) {
  for (const r of recs) {
    if (r.needLevel === 1) continue
    const bestAtPos = recs
      .filter((x) => x.player.pos === r.player.pos)
      .reduce((a, b) => ((b.player.pts ?? 0) > (a.player.pts ?? 0) ? b : a))
    const oldBonus = bestAtPos === r ? NEED_W[r.needLevel] * r.positionalDropoff : 0
    if (Math.abs(oldBonus - r.needBonus) > 0.051) {
      throw new Error(
        `reconstruction drifted on a level-${r.needLevel} candidate (${r.player.name}): ` +
          `${oldBonus.toFixed(2)} vs ${r.needBonus.toFixed(2)}`,
      )
    }
    if (Math.abs((r.player.vor ?? 0) - r.seatValue) > 0.051) {
      throw new Error(
        `a level-${r.needLevel} candidate was re-based off its own VOR (${r.player.name}): ` +
          `seatValue ${r.seatValue} vs vor ${r.player.vor}`,
      )
    }
  }
}

function slotOnClock(overall, size) {
  const round = Math.ceil(overall / size)
  const idx = overall - (round - 1) * size
  return round % 2 === 1 ? idx : size + 1 - idx
}

const REVERTS = ["both", "base", "bonus"]
const emptyStats = () => ({
  states: 0,
  flexStates: 0,
  ...Object.fromEntries(
    REVERTS.map((k) => [k, { flips: 0, clearFlips: 0, byOldPos: {}, byNewPos: {}, byRound: {} }]),
  ),
})

function runDraft(seed, mySlot, driveWith) {
  const rng = makeRng(seed * 7919 + mySlot)
  const drafted = new Set()
  const teams = Array.from({ length: N_TEAMS }, () => [])
  const stats = emptyStats()
  let controlChecked = false

  for (let overall = 1; overall <= ROUNDS * N_TEAMS; overall++) {
    const slot = slotOnClock(overall, N_TEAMS)
    const mine = teams[slot - 1]
    if (slot !== mySlot) {
      const p = cpuPick(rng, drafted, mine.map((x) => x.pos), Math.ceil(overall / N_TEAMS))
      if (!p) continue
      drafted.add(p.id)
      mine.push(p)
      continue
    }

    const recs = recommend({
      board,
      config,
      draftedIds: drafted,
      myPlayerIds: mine.map((p) => p.id),
      picksRemaining: ROUNDS - mine.length,
      limit: 400,
    })
    if (!recs.length) continue
    if (!controlChecked) {
      assertReconstructionIsExact(recs)
      controlChecked = true
    }

    const newTop = recs[0]
    const round = Math.ceil(overall / N_TEAMS)

    stats.states++
    // A state where the change COULD act at all: some candidate's only open seat is the flex.
    if (recs.some((r) => r.needLevel === 1)) stats.flexStates++

    let drivenBy = newTop.player
    for (const revert of REVERTS) {
      const rescored = oldOrder(recs, revert)
      const oldTop = rescored[0]
      if (revert === "both" && driveWith === "old") drivenBy = oldTop.player
      if (oldTop.player.id === newTop.player.id) continue
      const s = stats[revert]
      s.flips++
      // Margin far outside the 0.05 rounding of the fields read back, so a flip cannot be an
      // artifact of the reconstruction.
      const mine_ = rescored.find((r) => r.player.id === newTop.player.id)
      if (Math.abs(oldTop.oldScore - (mine_?.oldScore ?? 0)) > 0.5) s.clearFlips++
      s.byOldPos[`${oldTop.player.pos}-L${oldTop.needLevel}`] = (s.byOldPos[`${oldTop.player.pos}-L${oldTop.needLevel}`] ?? 0) + 1
      s.byNewPos[`${newTop.player.pos}-L${newTop.needLevel}`] = (s.byNewPos[`${newTop.player.pos}-L${newTop.needLevel}`] ?? 0) + 1
      s.byRound[round] = (s.byRound[round] ?? 0) + 1
    }

    drafted.add(drivenBy.id)
    mine.push(drivenBy)
  }
  return stats
}

const mergeInto = (a, b) => {
  for (const [k, v] of Object.entries(b)) a[k] = (a[k] ?? 0) + v
}
for (const driveWith of ["new", "old"]) {
  const tot = emptyStats()
  for (let seed = 1; seed <= SEEDS; seed++) {
    const s = runDraft(seed, ((seed - 1) % N_TEAMS) + 1, driveWith)
    tot.states += s.states
    tot.flexStates += s.flexStates
    for (const r of REVERTS) {
      tot[r].flips += s[r].flips
      tot[r].clearFlips += s[r].clearFlips
      mergeInto(tot[r].byOldPos, s[r].byOldPos)
      mergeInto(tot[r].byNewPos, s[r].byNewPos)
      mergeInto(tot[r].byRound, s[r].byRound)
    }
  }
  const pct = (n, d) => (d ? ((100 * n) / d).toFixed(1) + "%" : "—")
  console.log(`\n══ driving my picks with the ${driveWith.toUpperCase()} rule — ${configName}/${N_TEAMS}, ${SEEDS} drafts x ${ROUNDS} rounds ══`)
  console.log(`  my decision points                                            ${tot.states}`)
  console.log(`  ...with at least one FLEX-only candidate on the board         ${tot.flexStates} (${pct(tot.flexStates, tot.states)})`)
  for (const r of REVERTS) {
    const s = tot[r]
    console.log(`\n  reverting ${r.toUpperCase()}:`)
    console.log(`    top-pick FLIPS            ${s.flips} (${pct(s.flips, tot.states)} of all, ${pct(s.flips, tot.flexStates)} of FLEX-live)`)
    console.log(`    ...margin > 0.5 VOR       ${s.clearFlips}`)
    console.log(`    the pick TODAY would make ${JSON.stringify(s.byOldPos)}`)
    console.log(`    the pick it now makes     ${JSON.stringify(s.byNewPos)}`)
    console.log(`    by round                  ${JSON.stringify(s.byRound)}`)
  }
}
