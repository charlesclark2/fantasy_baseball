// NF-C6P2 — the POST-DRAFT ROSTER REPORT, computed from the SERVED league board.
//
// ═══════════════════════════════════════════════════════════════════════════════════════════════
// ⭐ WHAT THIS MODULE IS, AND — MORE IMPORTANTLY — WHAT IT IS NOT
// ═══════════════════════════════════════════════════════════════════════════════════════════════
//
// It is an AGGREGATOR. Every number it returns is a sum, a share, a rank or a difference of values
// the server already computed and served on `/fantasy/nfl/league-board`: `pts`, `ptsP10`, `ptsP90`,
// `vor`, `repl`, `g`, `bye`, plus the board's own `replacement` / `started` maps.
//
// ⛔ IT SCORES NOTHING. Not one stat weight is applied here, and that is deliberate rather than
// incidental: this codebase already carries THREE implementations of one scoring policy
// (`fantasy_engine` = the authority, `lib/league-scoring.ts` = the browser port, and
// `app/backend/services/league_scoring.py` = the Lambda port), pinned against each other by
// `test_nf_epic1_parity.py` because a silent drift means a user's board disagrees with the board we
// sell. A fourth would inherit that whole tax for no benefit. So the report consumes the OUTPUT of
// the server-side scorer and never re-derives it — which is also the only way it could work at all,
// since the raw stat line the scorer multiplies is PAID and never reaches this browser (NF-EPIC 1).
//
// ⛔ AND IT ISSUES NO QUERY. The whole report is one already-fetched payload. The E9.26b trap is
// specifically that a wide `lakehouse_query` inside the API Lambda FAILS SILENTLY and comes back
// `[]`, so the panel renders empty with no error anywhere; `/fantasy/nfl/league-board` is the
// narrowest served artifact that answers every output below — one league, one board, one roster.
//
// ═══════════════════════════════════════════════════════════════════════════════════════════════
// ⭐ THE HONEST-ANALYTICS RULES THIS FILE IS WRITTEN TO
// ═══════════════════════════════════════════════════════════════════════════════════════════════
//
//  1. THE PROJECTIONS ARE DISTRIBUTIONAL, so every headline total carries its 80% range and every
//     range states the assumption it was combined under (see `combineInterval`). ⛔ No point
//     estimate is presented as a forecast of what will happen.
//  2. NOTHING IS PREDICTED ABOUT AN OUTCOME. There is no "you will finish Nth", no win probability,
//     no "this is a playoff roster" — we have not measured any of those and `best_alpha = 0`. The
//     report describes the ROSTER against its own league's replacement level, which is exactly what
//     the served model supports.
//  3. AN ABSENCE IS REPORTED, NEVER IMPUTED. A roster row that did not match the board is counted
//     and named, never silently scored as zero (which would understate the team) and never dropped
//     without saying so. `ready` goes false rather than rendering a report from nothing — the
//     "honest empty state on absent data" the story requires (NF1.7 (a): a check that could not run
//     is not a pass).
//  4. THE WAIVER POOL IS BOUNDED HONESTLY. We cannot see the other eleven rosters, so "available"
//     is DEFINED as "outside the pool a league this size drafts" and the surface says so. Anything
//     stronger would be a claim about information we do not have.
//
// ═══════════════════════════════════════════════════════════════════════════════════════════════
// ⚠️ THE WEEKLY MODEL IS NOT SERVED YET, AND THAT SHAPES ONE OUTPUT
// ═══════════════════════════════════════════════════════════════════════════════════════════════
//
// The epic's architecture reads "season distributions + WEEKLY distributions IF AVAILABLE". NF-W1's
// weekly champion exists in the research tree but nothing publishes it, and the NFL ingest schedules
// that would feed it ship STOPPED (NF-INFRA1, an operator prerequisite). So the first-week lineup is
// built from the SEASON projection's own per-game rate (`pts / g` — expected points per game
// PLAYED, since `pts` already prices absence in and `g` is the expected games that produced it), and
// the surface labels it as exactly that. ⛔ It must never be presented as a week-1 projection; when
// a weekly artifact lands, `perGameRate` is the one function that changes.

import type { Player } from "@/lib/draft-optimizer"
import type { LeagueBoardPayload, RosterMatchRow } from "@/lib/fantasy"
import type { RosterSlotConfig } from "@/lib/league-config"
import { draftablePoolSize } from "@/lib/league-delta"

/** 80% two-sided normal quantile. Same constant as `lib/league-scoring.ts` and `scoring._Z80` —
 *  the bands we are recombining were produced with it, so recombining with anything else would
 *  silently change what "80%" means between the player rows and the team total. */
const Z80 = 1.2815515594

/** Slots that hold players but are never a starting spot, and never count as roster depth we can
 *  call on. Mirrors `league-delta.NON_DRAFT_SLOTS`' intent for the IR case. */
const NON_PLAYABLE_SLOTS = new Set(["IR", "TAXI"])

// ── The rostered player, joined ─────────────────────────────────────────────────────────────────

/** One roster row that DID match the board. The unmatched ones never enter the arithmetic; they are
 *  counted in `ReportCoverage` and named on the surface. */
export interface ReportPlayer {
  key: string
  name: string
  pos: string
  team: string | null
  bye: number | null
  /** The served board row. Non-null by construction — that is what makes this a `ReportPlayer`. */
  board: Player
  pts: number
  p10: number | null
  p90: number | null
  vor: number
  /** Expected games from the served model. Null/0 ⇒ no honest per-game rate exists for this row. */
  g: number | null
  /** The lineup slot this player fills, or null when they are on the bench. */
  slot: string | null
}

/** What the join could and could not see — rendered, never swallowed. */
export interface ReportCoverage {
  rosterRows: number
  matched: number
  unmatched: string[]
}

// ── Lineup construction ─────────────────────────────────────────────────────────────────────────

export interface LineupSlot {
  /** The league's own name for the slot ("RB", "FLEX", "SUPERFLEX"). */
  name: string
  eligible: string[]
  player: ReportPlayer | null
}

export interface Lineup {
  slots: LineupSlot[]
  bench: ReportPlayer[]
  /** Starting slots this roster cannot legally fill — a real, reportable state after a draft that
   *  went wrong, and the reason `fillLineup` returns slots rather than just a total. */
  unfilled: number
  total: number
}

/**
 * The best legal starting lineup, by a caller-supplied value.
 *
 * ⭐ MOST-RESTRICTIVE SLOT FIRST. A dedicated RB slot is filled before a FLEX, so a FLEX never
 * poaches the running back the RB slot still needed. That is the same ordering
 * `league_scoring.replacement_levels` uses on the server to allocate league-wide starter demand,
 * and using a different one here would put the report's lineup out of step with the replacement
 * levels every VOR on the board was computed against.
 *
 * ⚠️ THE GREEDY IS OPTIMAL ONLY FOR LAMINAR ELIGIBILITY (dedicated ⊂ FLEX ⊂ SUPERFLEX), which is
 * every real football roster shape. For a hypothetical league with genuinely crossing eligibility
 * sets it still returns a LEGAL lineup, just not provably the best one — which is why the surface
 * says "your best lineup" of a constructed thing and never claims optimality as a theorem.
 */
export function fillLineup(
  players: ReportPlayer[],
  roster: RosterSlotConfig[],
  value: (p: ReportPlayer) => number | null,
): Lineup {
  const spots: { name: string; eligible: string[] }[] = []
  for (const s of roster ?? []) {
    if (s?.bench) continue
    if (NON_PLAYABLE_SLOTS.has(String(s?.name ?? "").toUpperCase())) continue
    const count = Number(s?.count ?? 0)
    const eligible = (s?.eligible ?? []).filter(Boolean)
    if (!Number.isFinite(count) || count <= 0 || eligible.length === 0) continue
    for (let i = 0; i < count; i++) spots.push({ name: String(s.name), eligible })
  }
  // Ties keep declaration order, so two FLEX slots fill in the order the league declares them and
  // the lineup is deterministic for identical input.
  const ordered = spots
    .map((s, i) => ({ ...s, i }))
    .sort((a, b) => a.eligible.length - b.eligible.length || a.i - b.i)

  const taken = new Set<string>()
  const filled = new Map<number, ReportPlayer>()
  for (const spot of ordered) {
    let best: ReportPlayer | null = null
    let bestValue = -Infinity
    for (const p of players) {
      if (taken.has(p.key)) continue
      if (!spot.eligible.includes(p.pos)) continue
      const v = value(p)
      if (v == null || !Number.isFinite(v)) continue
      if (v > bestValue) {
        bestValue = v
        best = p
      }
    }
    if (best) {
      taken.add(best.key)
      filled.set(spot.i, best)
    }
  }

  const slots: LineupSlot[] = spots.map((s, i) => ({
    name: s.name,
    eligible: s.eligible,
    player: filled.get(i) ?? null,
  }))
  const bench = players.filter((p) => !taken.has(p.key))
  const total = slots.reduce((n, s) => n + (s.player?.pts ?? 0), 0)
  return { slots, bench, unfilled: slots.filter((s) => s.player == null).length, total }
}

// ── The team projection, and the one genuinely hard number on the page ──────────────────────────

export interface TeamProjection {
  /** Σ of the starters' expected points. EXACT under any dependence — expectation is linear. */
  total: number
  /** The 80% band, combined assuming player seasons are INDEPENDENT (`combineInterval`). */
  p10: number | null
  p90: number | null
  /** The same band if every season moved together — the widest reading. Reported as the stated
   *  outer bound so the independence assumption is bounded rather than merely disclosed. */
  correlatedP10: number | null
  correlatedP90: number | null
  starters: number
  unfilled: number
}

/**
 * Combine per-player 80% bands into one team band.
 *
 * ⚠️⚠️ THIS IS AN ASSUMPTION, NOT A MEASUREMENT, AND THE DIRECTION OF ITS ERROR IS KNOWN.
 * Independence is the standard combination and it UNDER-disperses a correlated sum — NF-W7b
 * measured exactly that on a DST leg assembled from independently-drawn components, where the
 * point score won and the coverage floor failed until a copula was fitted. Fantasy rosters co-move
 * for obvious reasons (one offense, shared game script, a stacked QB/WR pair), so the true band is
 * AT LEAST this wide.
 *
 * ⇒ we return BOTH ends of the admissible range — the independent band and the comonotone (every
 * season moves together) band, which is the naive sum of the player bounds — and the surface renders
 * the independent one with the comonotone one stated beside it. ⛔ Reporting only the independent
 * band and calling it "the team's 80% range" would be the NF-W7b defect on a user-facing surface.
 *
 * ⭐ EACH SIDE IS CARRIED SEPARATELY. Player bands are asymmetric by construction — `score_row`
 * floors `p10` at zero and carries each side by its own ratio, so a rookie's p10 sits near zero
 * while his p90 is a real season. Collapsing to one σ would throw that away; combining
 * `pts − p10` and `p90 − pts` independently preserves it and reduces to the symmetric answer when
 * the inputs are symmetric.
 */
export function combineInterval(
  rows: { pts: number; p10: number | null; p90: number | null }[],
): { p10: number | null; p90: number | null; correlatedP10: number | null; correlatedP90: number | null } {
  const usable = rows.filter((r) => r.p10 != null && r.p90 != null)
  // A partial band is not a band. If any starter is missing bounds the team band would silently
  // describe a different, smaller team than the total does — so we decline to draw one.
  if (usable.length === 0 || usable.length !== rows.length) {
    return { p10: null, p90: null, correlatedP10: null, correlatedP90: null }
  }
  const total = rows.reduce((n, r) => n + r.pts, 0)
  let varLo = 0
  let varHi = 0
  let sumLo = 0
  let sumHi = 0
  for (const r of rows) {
    const lo = Math.max(0, r.pts - (r.p10 as number))
    const hi = Math.max(0, (r.p90 as number) - r.pts)
    varLo += (lo / Z80) ** 2
    varHi += (hi / Z80) ** 2
    sumLo += r.p10 as number
    sumHi += r.p90 as number
  }
  return {
    p10: Math.max(0, total - Z80 * Math.sqrt(varLo)),
    p90: total + Z80 * Math.sqrt(varHi),
    correlatedP10: Math.max(0, sumLo),
    correlatedP90: sumHi,
  }
}

// ── Position strength ───────────────────────────────────────────────────────────────────────────

export interface PositionStrength {
  pos: string
  /** Your starters at this position, and what they are worth above this league's replacement. */
  starters: number
  startersPts: number
  startersVor: number
  /** What an AVERAGE team in this league holds at the position: the total VOR of the players the
   *  board expects to start league-wide, divided by the team count. */
  averageVor: number | null
  /** `startersVor − averageVor`. Positive ⇒ stronger than the average team here. */
  edge: number | null
  /** Rostered players at the position who are NOT in the starting lineup. */
  depth: number
}

/**
 * Per-position strength, measured against THIS league's own average team.
 *
 * ⭐ WHY VOR AND NOT POINTS. Raw points are not comparable across positions — a QB outscores a TE by
 * a wide margin in nearly every format, so a points table would report "your QB is your strength"
 * for every team in the league. VOR is the served, league-specific answer to that ("worth above the
 * player you could have for free"), and the board already carries it per row.
 *
 * ⭐ WHY THE BASELINE IS `started[pos] / n_teams` AND NOT THE REPLACEMENT LEVEL. Replacement is
 * already inside VOR; comparing to it again would just restate the same number. The interesting
 * comparison is against the other rosters in the league, and `board.started` is the server's own
 * count of how many at each position start league-wide once flex demand is allocated. The top
 * `started[pos]` board players are therefore the league's starting pool at that position, and their
 * mean VOR per team is what an average opponent holds.
 *
 * ⚠️ `started` is a LEAGUE-WIDE count (already multiplied by team count inside
 * `replacement_levels`), which is why it is divided by `n_teams` here and not multiplied. Getting
 * that backwards produces a baseline `n_teams²` too large and every position reads as a weakness.
 */
export function positionStrengths(
  mine: ReportPlayer[],
  lineup: Lineup,
  board: Player[],
  started: Record<string, number>,
  nTeams: number,
): PositionStrength[] {
  const startingKeys = new Set(
    lineup.slots.map((s) => s.player?.key).filter((k): k is string => !!k),
  )
  const positions = Array.from(new Set(mine.map((p) => p.pos))).sort()

  const byPos = new Map<string, Player[]>()
  for (const p of board) {
    if (p.pts == null || p.vor == null) continue
    const list = byPos.get(p.pos) ?? []
    list.push(p)
    byPos.set(p.pos, list)
  }

  return positions.map((pos) => {
    const at = mine.filter((p) => p.pos === pos)
    const starters = at.filter((p) => startingKeys.has(p.key))
    const startersPts = starters.reduce((n, p) => n + p.pts, 0)
    const startersVor = starters.reduce((n, p) => n + p.vor, 0)

    let averageVor: number | null = null
    const pool = byPos.get(pos)
    const demand = Number(started?.[pos] ?? 0)
    if (pool && Number.isFinite(demand) && demand > 0 && nTeams > 0) {
      const top = pool
        .slice()
        .sort((a, b) => (b.pts as number) - (a.pts as number))
        .slice(0, Math.round(demand))
      averageVor = top.reduce((n, p) => n + (p.vor as number), 0) / nTeams
    }

    return {
      pos,
      starters: starters.length,
      startersPts,
      startersVor,
      averageVor,
      edge: averageVor == null ? null : startersVor - averageVor,
      depth: at.length - starters.length,
    }
  })
}

// ── Bench quality ───────────────────────────────────────────────────────────────────────────────

export interface BenchQuality {
  count: number
  /** Bench players worth more than a freely-available replacement in this league. */
  aboveReplacement: number
  /** Total VOR held on the bench. Optionality, not points scored — the surface says so. */
  vor: number
  /** Bench players good enough to be starting on an average team in this league (their points clear
   *  the league-wide starter cutoff at their position) — the trade-surplus signal. */
  startable: ReportPlayer[]
}

export function benchQuality(
  bench: ReportPlayer[],
  board: Player[],
  started: Record<string, number>,
): BenchQuality {
  const cutoff = starterCutoffs(board, started)
  const startable = bench.filter((p) => {
    const c = cutoff.get(p.pos)
    return c != null && p.pts >= c
  })
  return {
    count: bench.length,
    aboveReplacement: bench.filter((p) => p.vor > 0).length,
    vor: bench.reduce((n, p) => n + p.vor, 0),
    startable,
  }
}

/** The points of the LAST player expected to start league-wide at each position — the line between
 *  "a starter somewhere in this league" and "somebody's bench". Derived from the board's own
 *  `started` demand, so it moves with league size, roster shape and superflex exactly as it should. */
export function starterCutoffs(
  board: Player[],
  started: Record<string, number>,
): Map<string, number> {
  const out = new Map<string, number>()
  const byPos = new Map<string, number[]>()
  for (const p of board) {
    if (p.pts == null) continue
    const list = byPos.get(p.pos) ?? []
    list.push(p.pts)
    byPos.set(p.pos, list)
  }
  for (const [pos, values] of byPos) {
    const demand = Math.round(Number(started?.[pos] ?? 0))
    if (!Number.isFinite(demand) || demand <= 0) continue
    const sorted = values.slice().sort((a, b) => b - a)
    const cut = sorted[Math.min(demand, sorted.length) - 1]
    if (cut != null) out.set(pos, cut)
  }
  return out
}

// ── Bye weeks ───────────────────────────────────────────────────────────────────────────────────

export interface ByeWeek {
  week: number
  /** Your rostered players idle that week. */
  out: ReportPlayer[]
  /** Starting slots you could not fill that week (from a real re-fill of the lineup). */
  unfilled: number
  /** Points per game the lineup loses that week, against your normal best lineup. Null when the
   *  per-game rate is unavailable for enough of the roster to make the comparison honest. */
  cost: number | null
}

/**
 * Expected points per game PLAYED.
 *
 * ⭐ `pts` ALREADY PRICES ABSENCE IN — the exporter's own note is "our points are an expected season
 * total; the chance he misses games is already priced in, which is why projected games sits beside
 * it". So `pts / g` is the rate for a week he plays, and it is the right quantity for a WEEKLY
 * comparison. Dividing by a fixed 17 instead would systematically understate a player the model
 * expects to miss time, i.e. would double-count his own availability discount.
 *
 * ⚠️ Null when `g` is missing or zero. The served board legitimately carries `g: 0` rows (a player
 * the model expects not to play), and 0 is exactly the divisor that would produce `Infinity` and
 * then a lineup made entirely of players who are not expected to play.
 */
export function perGameRate(p: ReportPlayer): number | null {
  if (p.g == null || !Number.isFinite(p.g) || p.g <= 0) return null
  return p.pts / p.g
}

export function byeWeeks(mine: ReportPlayer[], roster: RosterSlotConfig[]): ByeWeek[] {
  const weeks = Array.from(
    new Set(
      mine
        .map((p) => p.bye)
        .filter((w): w is number => typeof w === "number" && Number.isFinite(w)),
    ),
  ).sort((a, b) => a - b)

  // The reference is the best lineup by PER-GAME RATE — the same currency the weekly comparison is
  // made in. Comparing a bye-week lineup against the season-points lineup would mix two scales and
  // report a "cost" in units that are neither.
  const full = fillLineup(mine, roster, perGameRate)
  const fullRate = lineupRate(full)

  return weeks.map((week) => {
    const available = mine.filter((p) => p.bye !== week)
    const lineup = fillLineup(available, roster, perGameRate)
    const rate = lineupRate(lineup)
    return {
      week,
      out: mine.filter((p) => p.bye === week),
      unfilled: lineup.unfilled,
      cost: fullRate == null || rate == null ? null : Math.max(0, fullRate - rate),
    }
  })
}

/** Σ of a lineup's per-game rates, or null when any filled slot has no honest rate. */
export function lineupRate(lineup: Lineup): number | null {
  let total = 0
  for (const s of lineup.slots) {
    if (!s.player) continue
    const r = perGameRate(s.player)
    if (r == null) return null
    total += r
  }
  return total
}

// ── Fragility / injury concentration ────────────────────────────────────────────────────────────

export interface Fragility {
  /** Share of the starting lineup's projection carried by the single largest starter. */
  topShare: number | null
  /** …and by the top two. */
  topTwoShare: number | null
  /** Starters the served model expects to miss time (their `g` is below the board's full season). */
  atRisk: ReportPlayer[]
  /** Total expected games missed across the starting lineup, from the model's own `g`. */
  expectedGamesMissed: number | null
  /** The starting slot with the largest per-game drop if its starter is unavailable and the best
   *  bench body steps in — the thinnest point on the roster. */
  worstCover: { slot: string; player: ReportPlayer; replacement: ReportPlayer | null; drop: number } | null
}

/**
 * Where this roster is thin.
 *
 * ⚠️ "INJURY CONCENTRATION" IS NOT A NEW INJURY MODEL, and the wording on the surface has to keep
 * saying so. `g` is the served model's own expected games, already inside `pts`. All this does is
 * show WHERE that discount is concentrated and how much of the lineup one absence would move —
 * both of which are arithmetic on served values. ⛔ No probability of injury is computed, claimed or
 * implied anywhere on this path.
 */
export function fragility(lineup: Lineup, bench: ReportPlayer[], board: Player[]): Fragility {
  const starters = lineup.slots
    .map((s) => s.player)
    .filter((p): p is ReportPlayer => p != null)
  const total = starters.reduce((n, p) => n + p.pts, 0)
  const sorted = starters.slice().sort((a, b) => b.pts - a.pts)

  // The board's own full season — read from the data rather than hardcoded to 17, so a board built
  // for a different schedule length does not silently report every starter as "at risk".
  let fullSeason: number | null = null
  for (const p of board) {
    if (p.g != null && Number.isFinite(p.g) && (fullSeason == null || p.g > fullSeason)) {
      fullSeason = p.g
    }
  }

  const atRisk =
    fullSeason == null
      ? []
      : starters.filter((p) => p.g != null && Number.isFinite(p.g) && p.g < (fullSeason as number))
  const expectedGamesMissed =
    fullSeason == null
      ? null
      : starters.reduce(
          (n, p) => n + (p.g != null && Number.isFinite(p.g) ? (fullSeason as number) - p.g : 0),
          0,
        )

  let worstCover: Fragility["worstCover"] = null
  for (const slot of lineup.slots) {
    const player = slot.player
    if (!player) continue
    const rate = perGameRate(player)
    if (rate == null) continue
    // The best bench body that could legally take this slot. `null` is a real answer — an
    // uncovered slot — and it is reported as the full loss rather than skipped.
    let best: ReportPlayer | null = null
    let bestRate = 0
    for (const b of bench) {
      if (!slot.eligible.includes(b.pos)) continue
      const r = perGameRate(b)
      if (r == null) continue
      if (best == null || r > bestRate) {
        best = b
        bestRate = r
      }
    }
    const drop = rate - (best == null ? 0 : bestRate)
    if (worstCover == null || drop > worstCover.drop) {
      worstCover = { slot: slot.name, player, replacement: best, drop }
    }
  }

  return {
    topShare: total > 0 && sorted[0] ? sorted[0].pts / total : null,
    topTwoShare:
      total > 0 && sorted[0] && sorted[1] ? (sorted[0].pts + sorted[1].pts) / total : null,
    atRisk,
    expectedGamesMissed,
    worstCover,
  }
}

// ── Waiver + trade archetypes ───────────────────────────────────────────────────────────────────

export type WaiverKind = "bye-cover" | "thinnest-position" | "upside"

export interface WaiverIdea {
  kind: WaiverKind
  pos: string
  player: Player
  /** The reason, as a computed fact rather than a recommendation. */
  becausePos?: string
  becauseWeek?: number
}

/**
 * Likely-available players worth a look, in three archetypes.
 *
 * ⛔⛔ WE CANNOT SEE THE OTHER ROSTERS, so "available" is a DEFINITION, not an observation: a player
 * outside the pool a league this size drafts (`draftablePoolSize` = teams × drafted slots, the same
 * arithmetic `league-delta` already shows on screen). The surface states that definition next to
 * the list. Presenting these as "on waivers" would be a claim about information the product does not
 * have — the platform-import red line means we never hold the league's live rosters.
 */
export function waiverIdeas(
  board: Player[],
  mine: ReportPlayer[],
  poolSize: number | null,
  thinnestPos: string | null,
  worstByeWeek: { week: number; pos: string } | null,
): WaiverIdea[] {
  const owned = new Set(mine.map((p) => p.board.id))
  const available = board.filter(
    (p) =>
      !owned.has(p.id) &&
      p.pts != null &&
      (poolSize == null || (Number.isFinite(p.ovrRank) && p.ovrRank > poolSize)),
  )
  const bestAt = (pos: string): Player | null =>
    available
      .filter((p) => p.pos === pos)
      .sort((a, b) => (b.vor ?? -Infinity) - (a.vor ?? -Infinity))[0] ?? null

  const out: WaiverIdea[] = []
  if (worstByeWeek) {
    const p = bestAt(worstByeWeek.pos)
    if (p) out.push({ kind: "bye-cover", pos: p.pos, player: p, becauseWeek: worstByeWeek.week })
  }
  if (thinnestPos) {
    const p = bestAt(thinnestPos)
    if (p && !out.some((o) => o.player.id === p.id)) {
      out.push({ kind: "thinnest-position", pos: p.pos, player: p, becausePos: thinnestPos })
    }
  }
  // ⭐ UPSIDE IS THE INTERVAL, NOT A HUNCH: the widest gap between the 80% top of a player's band and
  // his point estimate. That is the distributional product's own answer to "who could be much more
  // than this", and it is the reason the ranges are on every row in the first place.
  const upside = available
    .filter((p) => p.ptsP90 != null && p.pts != null)
    .sort((a, b) => (b.ptsP90 as number) - (b.pts as number) - ((a.ptsP90 as number) - (a.pts as number)))
    .find((p) => !out.some((o) => o.player.id === p.id))
  if (upside) out.push({ kind: "upside", pos: upside.pos, player: upside })
  return out
}

export interface TradeIdea {
  /** A position you hold startable depth at. */
  from: string
  /** …and the one your starters are thinnest at. */
  to: string
  surplus: ReportPlayer[]
}

/**
 * The one trade SHAPE the data supports: you hold a bench player who would start on an average team
 * in this league, at a position where you are already strong, and you are below the average team
 * somewhere else.
 *
 * ⛔ NO ACCEPTANCE MODELLING, no "fair value", no named counterparty. Trade utility and acceptance
 * are a later story in the epic (§14+) and nothing here has been validated against a real trade
 * market — so this reports a fact about the roster and stops.
 */
export function tradeIdeas(
  positions: PositionStrength[],
  bench: BenchQuality,
): TradeIdea[] {
  const ranked = positions.filter((p) => p.edge != null).sort((a, b) => (a.edge as number) - (b.edge as number))
  const weakest = ranked[0]
  if (!weakest || bench.startable.length === 0) return []
  const byPos = new Map<string, ReportPlayer[]>()
  for (const p of bench.startable) {
    if (p.pos === weakest.pos) continue // depth at the weak spot is not a surplus to trade FROM
    byPos.set(p.pos, [...(byPos.get(p.pos) ?? []), p])
  }
  return Array.from(byPos.entries())
    .sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]))
    .slice(0, 2)
    .map(([from, surplus]) => ({ from, to: weakest.pos, surplus }))
}

// ── The report ──────────────────────────────────────────────────────────────────────────────────

/** Why a report could not be produced. Each one renders a DIFFERENT honest empty state — "we have
 *  no data" and "your league has not drafted" are different facts and must not share a message. */
export type NotReadyReason =
  | "no-league"
  | "no-team-linked"
  | "not-drafted"
  | "no-board"
  | "nothing-matched"

export interface RosterReport {
  ready: true
  league: LeagueBoardPayload["league"]
  coverage: ReportCoverage
  players: ReportPlayer[]
  lineup: Lineup
  projection: TeamProjection
  positions: PositionStrength[]
  bench: BenchQuality
  byes: ByeWeek[]
  fragility: Fragility
  waivers: WaiverIdea[]
  trades: TradeIdea[]
  /** The best lineup by per-game rate with week-1 byes removed — the "first week" view. */
  firstWeek: Lineup
  /** teams × drafted slots, or null when the roster shape does not say. Rendered, so the waiver
   *  pool's definition is visible arithmetic rather than a hidden constant. */
  poolSize: number | null
}

export type RosterReportResult = RosterReport | { ready: false; reason: NotReadyReason }

/** The NFL's first regular-season week. Only used to drop byes from the first-week lineup; no real
 *  team has a week-1 bye, so this is a correctness guard rather than a behaviour. */
const FIRST_WEEK = 1

export function buildRosterReport(payload: LeagueBoardPayload | null | undefined): RosterReportResult {
  if (!payload?.league) return { ready: false, reason: "no-league" }
  const board = payload.board?.players ?? []
  if (board.length === 0) return { ready: false, reason: "no-board" }

  const league = payload.league
  const rows: RosterMatchRow[] = payload.roster ?? []
  if (rows.length === 0) {
    // A linked team with an empty roster is the ordinary PRE-DRAFT state (both ESPN and Sleeper warn
    // about it at import time), and it is NOT the same as never picking a team — conflating the two
    // told a real user to "go pick a team" they had already picked (NF-C6's own shipped bug).
    return {
      ready: false,
      reason: league.source_team_key ? "not-drafted" : "no-team-linked",
    }
  }

  const players: ReportPlayer[] = []
  const unmatched: string[] = []
  for (const row of rows) {
    const b = row.board
    const name = String(row.roster?.name ?? "").trim()
    if (!b || b.pts == null || b.vor == null) {
      unmatched.push(name || String(row.roster?.player_key ?? "unknown"))
      continue
    }
    players.push({
      key: String(row.roster?.player_key ?? b.id),
      name: b.name ?? name,
      pos: b.pos,
      team: b.team ?? null,
      bye: b.bye ?? null,
      board: b,
      pts: b.pts,
      p10: b.ptsP10 ?? null,
      p90: b.ptsP90 ?? null,
      vor: b.vor,
      g: b.g ?? null,
      slot: null,
    })
  }
  const coverage: ReportCoverage = {
    rosterRows: rows.length,
    matched: players.length,
    unmatched,
  }
  if (players.length === 0) return { ready: false, reason: "nothing-matched" }

  const rosterShape = league.roster ?? []
  const lineup = fillLineup(players, rosterShape, (p) => p.pts)
  for (const s of lineup.slots) if (s.player) s.player.slot = s.name

  const starters = lineup.slots
    .map((s) => s.player)
    .filter((p): p is ReportPlayer => p != null)
  const band = combineInterval(starters.map((p) => ({ pts: p.pts, p10: p.p10, p90: p.p90 })))

  const started = payload.board?.started ?? {}
  const nTeams = Number(league.n_teams ?? 0)
  const positions = positionStrengths(players, lineup, board, started, nTeams)
  const bench = benchQuality(lineup.bench, board, started)
  const byes = byeWeeks(players, rosterShape)

  const ranked = positions
    .filter((p) => p.edge != null && p.starters > 0)
    .sort((a, b) => (a.edge as number) - (b.edge as number))
  const thinnestPos = ranked[0]?.pos ?? null

  // The bye week that hurts most, and the position it hurts at — used to aim the bye-cover idea.
  const worstBye = byes
    .filter((b) => b.cost != null)
    .sort((a, b) => (b.cost as number) - (a.cost as number))[0]
  const worstByeWeek = worstBye
    ? {
        week: worstBye.week,
        pos:
          worstBye.out
            .slice()
            .sort((a, b) => b.pts - a.pts)[0]?.pos ?? (thinnestPos ?? ""),
      }
    : null

  return {
    ready: true,
    league,
    coverage,
    players,
    lineup,
    projection: {
      total: lineup.total,
      p10: band.p10,
      p90: band.p90,
      correlatedP10: band.correlatedP10,
      correlatedP90: band.correlatedP90,
      starters: starters.length,
      unfilled: lineup.unfilled,
    },
    positions,
    bench,
    byes,
    fragility: fragility(lineup, lineup.bench, board),
    waivers: waiverIdeas(
      board,
      players,
      draftablePoolSize(league),
      thinnestPos,
      worstByeWeek && worstByeWeek.pos ? worstByeWeek : null,
    ),
    trades: tradeIdeas(positions, bench),
    firstWeek: fillLineup(
      players.filter((p) => p.bye !== FIRST_WEEK),
      rosterShape,
      perGameRate,
    ),
    poolSize: draftablePoolSize(league),
  }
}
