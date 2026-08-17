// mock-draft.ts — the CPU opponents and the post-draft grade for the mock draft simulator (NF-C2.1).
//
// The live tool (MVP-3) makes the user type in what the room did. This module IS the room: it picks
// for every other seat so a user can practise a draft in the off-season, or rehearse a slot before
// the real thing. Everything here is PURE and SEEDED — the same (seed, state) always produces the
// same pick — which is what lets the UI reveal CPU picks on a timer while a "skip to my pick"
// button resolves the identical picks instantly, and what lets the guard suite assert on behaviour
// instead of on "something happened".
//
// ══ WHAT THE CPU REASONS OFF, AND WHY IT IS BOTH SOURCES ══════════════════════════════════════
//
// A mock room that drafts pure ADP is a market replay: it never takes a player the market is wrong
// about, so practising against it teaches you the market. A room that drafts pure projection is a
// mirror of our own board: every opponent wants exactly who our recommendations want, which makes
// the tool look far better than it is. Neither is a real draft.
//
// So each CPU seat gets a seeded PERSONA blending the two orders — `marketWeight` ∈ [0.45, 0.95],
// i.e. every opponent is at least somewhat market-anchored (real rooms are) and none is a pure
// ADP robot. Two consequences worth stating because they are the point of the feature:
//
//   · players our board likes and the market does not FALL, so the user gets to practise taking
//     them (and sees, in the grade, what that was worth on our numbers);
//   · players the market loves go roughly when the market says, so the user cannot simply sit and
//     wait for a consensus first-rounder in round 4.
//
// ⚠️ HONEST FRAMING (best_alpha = 0). Nothing here is a claim that our board beats ADP or that a
// good mock grade means a good season. The CPU is a PRACTICE OPPONENT, and the grade scores the
// room on OUR projections — the same numbers the recommendation panel already used — which is a
// circular measure and is labelled as one wherever it is shown (`GRADE_CIRCULARITY_NOTE`).
//
// ⚠️ MARKET COVERAGE IS PARTIAL AND THAT IS A REAL SIGNAL, NOT A GAP TO FILL. On the served board
// only the players inside the ADP sample carry `adp` (226 of 858 on the 2026 full-PPR/12 export);
// the rest are genuinely undrafted in that sample. `marketOrder` puts them AFTER every ADP'd
// player rather than inventing a number for them — see its note.

import {
  assignRoster,
  openEligibility,
  openStarterSlots,
  needLevel,
  rosterRequirements,
  slotOnClock,
  type FilledSlot,
  type LeagueConfigMeta,
  type Player,
} from "@/lib/draft-optimizer"

// ── seeded randomness ───────────────────────────────────────────────────────────────────────────
//
// ⭐ THE RNG IS RE-DERIVED PER PICK, NEVER CARRIED. A single mutable generator threaded through the
// draft would make the result depend on HOW MANY picks were drawn in one batch — so the timer path
// (one pick per tick) and the "skip to my pick" path (many picks in one synchronous loop) would
// diverge, and a mock draft would not survive a reload. Seeding each pick on (seed, overallPick)
// makes every pick a pure function of the state it is made from. Pinned by the guard suite.

/** FNV-1a-ish mix of a small number of 32-bit inputs. */
export function hashSeed(...parts: number[]): number {
  let h = 2166136261 >>> 0
  for (const p of parts) {
    h ^= Math.imul(p >>> 0, 0x9e3779b1) >>> 0
    h = Math.imul(h ^ (h >>> 15), 2246822507) >>> 0
    h = (h ^ (h >>> 13)) >>> 0
  }
  return h >>> 0
}

/** mulberry32 — small, fast, and good enough for draft jitter. */
export function makeRng(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Standard normal via Box–Muller. */
function gaussian(rng: () => number): number {
  const u = Math.max(rng(), 1e-9)
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rng())
}

/** A random draft seed, for a fresh mock. Exposed so the UI can show it and a user can re-run one. */
export function randomSeed(): number {
  return Math.floor(Math.random() * 0xffffffff) >>> 0
}

// ── the market order ────────────────────────────────────────────────────────────────────────────

/**
 * `{playerId -> market rank}`, 1-based, over the WHOLE board.
 *
 * ⭐ A ROW WITHOUT `adp` IS NOT MISSING DATA — the ADP sample simply never drafted him, which is
 * exactly the information a mock room should act on. Inventing a market rank for him (interpolating
 * from our own projection, say) would quietly turn our opinion into "the market's" and then let the
 * CPU take him at that price, which is the one thing this whole module must not do. So every
 * un-ADP'd row is placed AFTER every ADP'd one, ordered among themselves by our board. In practice
 * that means the market half of a persona's blend runs out at the edge of the sample and the
 * projection half takes over — the honest behaviour, since past the sample the market has no view.
 */
export function marketOrder(board: Player[]): Map<string, number> {
  const withAdp = board.filter((p) => p.adp != null)
  const withoutAdp = board.filter((p) => p.adp == null)
  withAdp.sort((a, b) => (a.adp as number) - (b.adp as number) || a.id.localeCompare(b.id))
  withoutAdp.sort((a, b) => (a.ovrRank ?? 1e9) - (b.ovrRank ?? 1e9) || a.id.localeCompare(b.id))
  const m = new Map<string, number>()
  ;[...withAdp, ...withoutAdp].forEach((p, i) => m.set(p.id, i + 1))
  return m
}

/** How many rows the ADP sample actually covers — the point past which `marketOrder` is our order. */
export function marketDepth(board: Player[]): number {
  return board.reduce((n, p) => n + (p.adp != null ? 1 : 0), 0)
}

// ── opponent personas ───────────────────────────────────────────────────────────────────────────

export interface CpuPersona {
  slot: number
  /** Weight on the MARKET order vs our board, in [0,1]. 1.0 would be a pure ADP robot; the sampled
   *  range never reaches either end, because neither extreme is a real drafter. */
  marketWeight: number
  /** Multiplier on the per-round noise — how much this seat reaches or waits. */
  varianceMult: number
  label: string
}

const MARKET_W_MIN = 0.45
const MARKET_W_MAX = 0.95
const VARIANCE_MULT_MIN = 0.7
const VARIANCE_MULT_MAX = 1.4

/** Deterministic per (seed, slot), so the same room replays identically and each seat keeps its
 *  character all draft long — a team that reached in round 2 is still the team that reaches. */
export function personaFor(seed: number, slot: number): CpuPersona {
  const rng = makeRng(hashSeed(seed, slot, 0x9e37))
  const marketWeight = MARKET_W_MIN + rng() * (MARKET_W_MAX - MARKET_W_MIN)
  const varianceMult = VARIANCE_MULT_MIN + rng() * (VARIANCE_MULT_MAX - VARIANCE_MULT_MIN)
  const label =
    marketWeight > 0.8
      ? varianceMult > 1.1
        ? "Chalk, jumpy"
        : "Sticks to ADP"
      : marketWeight < 0.6
        ? "Values projections"
        : varianceMult > 1.1
          ? "Streaky"
          : "Balanced"
  return { slot, marketWeight, varianceMult, label }
}

// ── the pick ────────────────────────────────────────────────────────────────────────────────────

// Noise on the blended RANK, in rank units, widening with the round. Real rooms are near-consensus
// at the top and scatter badly by the double-digit rounds, which is the shape these produce: ~±6
// spots in round 1 against ~±40 by round 12. Deliberately plain constants — a mock opponent is a
// practice partner, not a fitted model, and pretending otherwise by tuning them against anything
// would be a claim we have not earned.
const SIGMA_BASE = 6
const SIGMA_PER_ROUND = 3.2
const SIGMA_MAX = 45
/** How deep a CPU looks. A real drafter compares a shortlist, not 800 players, and bounding it also
 *  bounds the work per pick (858 rows × ~200 picks stays trivially fast). */
const CONSIDER = 40

export interface CpuChoice {
  player: Player
  /** The 1-based market rank used in the blend. `null` when the player is outside the ADP sample —
   *  rendered as "outside ADP", never as a number we made up. */
  marketRank: number | null
  reason: string
  needLevel: number
  mustFill: boolean
}

export interface CpuPickArgs {
  board: Player[]
  config: LeagueConfigMeta
  /** Every pick made so far, in order. */
  picks: { id: string; slot: number }[]
  /** The seat picking now. */
  slot: number
  nTeams: number
  seed: number
  market: Map<string, number>
  /** Rank-in-our-board lookup; defaults to `ovrRank`. */
  boardRank?: Map<string, number>
}

/** Board rank by our own numbers — `ovrRank` where the exporter set one, else VOR order. */
export function boardOrder(board: Player[]): Map<string, number> {
  const ranked = [...board].sort(
    (a, b) => (a.ovrRank ?? 1e9) - (b.ovrRank ?? 1e9) || (b.vor ?? -1e9) - (a.vor ?? -1e9) || a.id.localeCompare(b.id),
  )
  const m = new Map<string, number>()
  ranked.forEach((p, i) => m.set(p.id, i + 1))
  return m
}

/**
 * One CPU pick. Returns `null` only if the seat has no legal player left at all.
 *
 * The legality rules are deliberately the SAME ones the optimizer enforces for the user, so the
 * room drafts rosters that are actually legal and the grade compares like with like:
 *
 *   · a player must fit a slot this team still has open (`openEligibility`);
 *   · once every remaining pick is spoken for by an open STARTER slot, only fillers are considered
 *     (the reserve constraint — without it CPU teams finish with empty starters and the whole
 *     room's projected-points comparison is against illegal lineups);
 *   · low-predictability positions (K/DST) are held back until that constraint binds, which is
 *     what real rooms do and what `recommend` does. The composition is the same one documented
 *     there: whenever K/DST are all a roster can still accept, the constraint is NECESSARILY
 *     binding, so they come back — never early, always by the end.
 */
export function cpuPick(args: CpuPickArgs): CpuChoice | null {
  const { board, config, picks, slot, nTeams, seed, market } = args
  const boardRank = args.boardRank ?? boardOrder(board)
  const persona = personaFor(seed, slot)

  const overallPick = picks.length + 1
  const round = Math.floor((overallPick - 1) / nTeams) + 1

  const drafted = new Set(picks.map((p) => p.id))
  const byId = new Map(board.map((p) => [p.id, p]))
  const mine = picks.filter((p) => p.slot === slot).map((p) => byId.get(p.id)).filter(Boolean) as Player[]

  const eligible = openEligibility(mine, config.roster)
  if (eligible.size === 0) return null // roster full

  const req = rosterRequirements(config.roster)
  const open = openStarterSlots(mine.map((p) => p.pos), req)
  const totalSlots = config.roster.reduce((a, s) => a + s.count, 0)
  const picksRemaining = totalSlots - mine.length
  const openStarterCount = Object.values(open.dedicated).reduce((a, n) => a + n, 0) + open.flex.length
  const mustFillNow = openStarterCount > 0 && picksRemaining <= openStarterCount

  const depth = board.length
  const pool: { p: Player; key: number; level: number }[] = []
  for (const p of board) {
    if (drafted.has(p.id)) continue
    if (p.vor == null) continue // a genuinely unprojected gap-fill row is not a draftable player
    if (!eligible.has(p.pos)) continue
    const level = needLevel(open, p.pos)
    if (mustFillNow && level === 0) continue
    if (p.lowPred === true && !mustFillNow) continue
    const mr = market.get(p.id) ?? depth
    const br = boardRank.get(p.id) ?? depth
    // The blend is over RANKS, not scores, so the two sources are on one comparable scale
    // regardless of how either is distributed.
    let key = persona.marketWeight * mr + (1 - persona.marketWeight) * br
    // A position this seat still needs to start is worth moving up the list for. Small and flat:
    // enough to stop a room drafting six wide receivers, not enough to swamp the blend.
    if (level === 2) key *= 0.82
    else if (level === 1) key *= 0.92
    pool.push({ p, key, level })
  }
  if (pool.length === 0) return null

  pool.sort((a, b) => a.key - b.key || a.p.id.localeCompare(b.p.id))
  const shortlist = pool.slice(0, CONSIDER)

  const sigma = Math.min(SIGMA_MAX, SIGMA_BASE + SIGMA_PER_ROUND * (round - 1)) * persona.varianceMult
  // ⭐ ONE RNG PER PICK, DRAWN OVER A DETERMINISTICALLY-ORDERED SHORTLIST — see the note at the top
  // of the file. Both properties are load-bearing for replay.
  const rng = makeRng(hashSeed(seed, overallPick, slot))
  let best = shortlist[0]
  let bestScore = Infinity
  for (const c of shortlist) {
    const score = c.key + sigma * gaussian(rng)
    if (score < bestScore) {
      bestScore = score
      best = c
    }
  }

  const marketRank = market.get(best.p.id) ?? null
  const inSample = best.p.adp != null
  return {
    player: best.p,
    marketRank: inSample ? (marketRank as number) : null,
    needLevel: best.level,
    mustFill: mustFillNow,
    reason: cpuReason(best.p, best.level, mustFillNow, inSample ? (marketRank as number) : null, overallPick),
  }
}

/** A short, literal account of why the seat took him. Descriptive only — it reports what the pick
 *  WAS relative to the market and the roster, and claims nothing about whether it was good. */
function cpuReason(
  player: Player,
  level: number,
  mustFill: boolean,
  marketRank: number | null,
  overallPick: number,
): string {
  const parts: string[] = []
  if (mustFill) parts.push(`had to fill a starter`)
  else if (level === 2) parts.push(`needed a ${player.pos}`)
  else if (level === 1) parts.push(`FLEX need`)
  if (marketRank == null) {
    parts.push("outside the ADP sample")
  } else {
    const delta = Math.round(marketRank - overallPick)
    if (delta >= 8) parts.push(`fell ${delta} past ADP`)
    else if (delta <= -8) parts.push(`reached ${-delta} early`)
    else parts.push(`about ADP`)
  }
  return parts.join(" · ")
}

// ── the sim loop ────────────────────────────────────────────────────────────────────────────────

export interface Pick {
  id: string
  slot: number
}

export interface SimArgs {
  board: Player[]
  config: LeagueConfigMeta
  picks: Pick[]
  nTeams: number
  mySlot: number
  seed: number
  /** Total picks this mock runs to — `rounds * nTeams`. */
  maxPicks: number
  market: Map<string, number>
  boardRank?: Map<string, number>
  /** Stop after this many CPU picks (the timer path passes 1). Unset = run to the user's turn. */
  limit?: number
}

/**
 * Advance the room: make CPU picks from the current state until it is the user's turn again, the
 * board runs dry, or `maxPicks` is reached. Returns the picks to APPEND (never mutates).
 *
 * ⭐ `limit: 1` and an unlimited call must produce the same sequence — that is the whole reason the
 * RNG is re-derived per pick, and it is what makes "skip to my pick" a fast-forward rather than a
 * different draft. Pinned by the guard suite.
 */
export function simulateCpuPicks(args: SimArgs): { picks: Pick[]; choices: CpuChoice[] } {
  const { board, config, nTeams, mySlot, seed, maxPicks, market, limit } = args
  const boardRank = args.boardRank ?? boardOrder(board)
  const out: Pick[] = []
  const choices: CpuChoice[] = []
  const running = [...args.picks]

  while (running.length < maxPicks) {
    const slot = slotOnClock(running.length + 1, nTeams)
    if (slot === mySlot) break
    if (limit != null && out.length >= limit) break
    const choice = cpuPick({ board, config, picks: running, slot, nTeams, seed, market, boardRank })
    if (!choice) break // this seat has nothing legal left; stop rather than stall on a dead loop
    const pick: Pick = { id: choice.player.id, slot }
    running.push(pick)
    out.push(pick)
    choices.push(choice)
  }
  return { picks: out, choices }
}

// ── the post-draft grade ────────────────────────────────────────────────────────────────────────

/**
 * ⚠️ THE CAVEAT THAT MUST TRAVEL WITH EVERY GRADE. The room is ranked on OUR projected starter
 * points — the same numbers the recommendation panel was built to maximise — while the CPU seats
 * draft partly off market ADP. A user who follows the recommendations will therefore tend to rank
 * well BY CONSTRUCTION, and that is a fact about the measure, not evidence about the season.
 *
 * Exported (rather than written inline in the component) so the guard suite can assert the shipped
 * screen carries this exact sentence — a grade that loses it is an overclaim.
 */
export const GRADE_CIRCULARITY_NOTE =
  "This ranks the room on our own projections — the same numbers the recommendations use — while the CPU teams draft partly off market ADP. A high finish here means you followed this board closely, not that you would win a real league."

export interface TeamGrade {
  slot: number
  isMe: boolean
  starterPoints: number
  startersFilled: number
  starterSlots: number
  roster: FilledSlot[]
}

export interface PickValue {
  player: Player
  overallPick: number
  marketRank: number | null
  /** Market rank minus the pick it was actually made at. Positive = he was still there later than
   *  the market says he goes. `null` outside the ADP sample, where there is no market view to
   *  compare against — NOT zero, which would read as "went exactly at ADP". */
  vsMarket: number | null
}

export interface PositionGrade {
  pos: string
  mine: number
  roomMedian: number
}

export interface DraftGrade {
  teams: TeamGrade[]
  me: TeamGrade
  myRank: number
  nTeams: number
  roomMedian: number
  positions: PositionGrade[]
  steals: PickValue[]
  reaches: PickValue[]
}

const median = (xs: number[]): number => {
  if (xs.length === 0) return 0
  const s = [...xs].sort((a, b) => a - b)
  const m = Math.floor(s.length / 2)
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}

/** Positions that carry a starter slot in this config — the axes a per-position comparison can
 *  honestly be drawn on. */
function starterPositions(config: LeagueConfigMeta): string[] {
  const out: string[] = []
  for (const s of config.roster) {
    if (s.bench) continue
    for (const e of s.eligible) if (!out.includes(e)) out.push(e)
  }
  return out
}

export function gradeDraft(args: {
  board: Player[]
  config: LeagueConfigMeta
  picks: Pick[]
  nTeams: number
  mySlot: number
  market: Map<string, number>
}): DraftGrade {
  const { board, config, picks, nTeams, mySlot, market } = args
  const byId = new Map(board.map((p) => [p.id, p]))

  const teams: TeamGrade[] = []
  for (let slot = 1; slot <= nTeams; slot++) {
    const players = picks
      .filter((p) => p.slot === slot)
      .map((p) => byId.get(p.id))
      .filter(Boolean) as Player[]
    const roster = assignRoster(players, config.roster)
    const starterSlots = roster.filter((s) => !s.bench)
    const filled = starterSlots.filter((s) => s.player)
    teams.push({
      slot,
      isMe: slot === mySlot,
      starterPoints: Math.round(filled.reduce((a, s) => a + (s.player?.pts ?? 0), 0)),
      startersFilled: filled.length,
      starterSlots: starterSlots.length,
      roster,
    })
  }

  const me = teams.find((t) => t.isMe) as TeamGrade
  const sorted = [...teams].sort((a, b) => b.starterPoints - a.starterPoints)
  const myRank = sorted.findIndex((t) => t.slot === mySlot) + 1

  // Per position: the points MY starters at that position project, against the room's median for
  // the same position. Bench players are excluded on both sides — a position is only as strong as
  // what it starts.
  const positions: PositionGrade[] = []
  for (const pos of starterPositions(config)) {
    const at = (t: TeamGrade) =>
      t.roster.filter((s) => !s.bench && s.player?.pos === pos).reduce((a, s) => a + (s.player?.pts ?? 0), 0)
    positions.push({ pos, mine: Math.round(at(me)), roomMedian: Math.round(median(teams.map(at))) })
  }

  // My picks, priced against the market order. Only rows inside the ADP sample can be priced.
  const myPicks: PickValue[] = []
  picks.forEach((p, i) => {
    if (p.slot !== mySlot) return
    const player = byId.get(p.id)
    if (!player) return
    const inSample = player.adp != null
    const marketRank = inSample ? (market.get(p.id) ?? null) : null
    myPicks.push({
      player,
      overallPick: i + 1,
      marketRank,
      vsMarket: marketRank == null ? null : Math.round(marketRank - (i + 1)),
    })
  })
  const priced = myPicks.filter((p) => p.vsMarket != null)
  const steals = [...priced].sort((a, b) => (b.vsMarket as number) - (a.vsMarket as number)).slice(0, 3)
  const reaches = [...priced].sort((a, b) => (a.vsMarket as number) - (b.vsMarket as number)).slice(0, 3)

  return {
    teams,
    me,
    myRank,
    nTeams,
    roomMedian: Math.round(median(teams.map((t) => t.starterPoints))),
    positions,
    steals: steals.filter((s) => (s.vsMarket as number) > 0),
    reaches: reaches.filter((s) => (s.vsMarket as number) < 0),
  }
}
