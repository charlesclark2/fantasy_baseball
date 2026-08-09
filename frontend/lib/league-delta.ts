// G100-C1 — the generic-vs-your-league DELTA. The activation moment, as arithmetic.
//
// ══ WHAT THIS COMPARES, AND WHAT IT DOES NOT ═══════════════════════════════════════════════════
//
// TWO OF OUR OWN BOARDS: the free preset (`full_ppr` at 12 teams — `entitlement.FREE_BOARD_CONFIG`)
// and the same season projection re-scored for the caller's saved league. Nothing here touches ADP,
// consensus, or anyone else's rankings.
//
// ⛔ THAT DISTINCTION IS THE WHOLE HONESTY RISK ON THIS SURFACE. A column headed "movement" on a
// fantasy board means "versus the market" everywhere else in the category, so a reader imports that
// reading unless the page states otherwise — which is why `LEAGUE_DELTA_DEFINITION` is rendered
// beside the table rather than kept in a tooltip. A delta between two of our boards measures HOW
// MUCH THE READER'S SETTINGS MATTER. It is not an edge, and `best_alpha = 0`.
//
// ══ WHY IT IS A PURE MODULE ════════════════════════════════════════════════════════════════════
//
// Same reasoning as `league-scoring.ts`: pure and synchronous, so it is testable without a browser
// and re-runs instantly on an edit. It also keeps the component free of the two arithmetic traps
// below, which are the parts most likely to be written wrong.

import type { Player } from "@/lib/draft-optimizer"

export interface PlayerDelta {
  id: string
  name: string
  pos: string
  team: string | null
  /** Rank on the free preset board. Null when the player is not ON it (see `onlyInLeague`). */
  genericOvrRank: number | null
  genericPosRank: number | null
  genericVor: number | null
  /** Rank on the caller's league board. */
  leagueOvrRank: number
  leaguePosRank: number
  leagueVor: number | null
  leaguePts: number | null
  /**
   * Places GAINED overall: `generic − league`, so POSITIVE means the player moved UP (toward rank
   * 1) in this league. Null when he is on only one of the two boards.
   *
   * ⚠️ THE SIGN IS THE EASIEST THING HERE TO GET BACKWARDS, because rank is an inverted scale: a
   * SMALLER number is BETTER, so the intuitive `league − generic` yields a negative number for a
   * player who improved. It is spelled this way round once, here, and every consumer reads
   * "positive = riser" — rather than each component re-deciding and one of them getting it wrong.
   */
  ovrDelta: number | null
  posDelta: number | null
  /** VOR gained in this league's scoring. Positive = worth more here. */
  vorDelta: number | null
  /** On the league board but NOT the free one — e.g. a superflex league ranking a QB the free
   *  board's roster shape leaves unranked. A rank delta is UNDEFINED for these, not zero. */
  onlyInLeague: boolean
}

export interface PositionShift {
  pos: string
  genericReplacement: number | null
  leagueReplacement: number | null
  /** League minus generic. Positive = replacement level is HIGHER here, so the position is
   *  shallower and its players are worth LESS above the baseline. */
  replacementDelta: number | null
  /** How many players at this position clear replacement in each board — the "how many actually
   *  matter" number a drafter reasons with. */
  genericStartable: number | null
  leagueStartable: number | null
}

export interface LeagueDelta {
  /** Every player on the league board that we could compare, biggest absolute move first. */
  players: PlayerDelta[]
  risers: PlayerDelta[]
  fallers: PlayerDelta[]
  positions: PositionShift[]
  /** How many players moved at least `MEANINGFUL_MOVE` places overall — the one-line summary. */
  meaningfulMoves: number
  /** Players compared on both boards. A denominator, so "14 of 312 moved" is readable. */
  compared: number
}

/**
 * How many places a player must move before the screen calls it a move.
 *
 * ⚠️ A PRESENTATION THRESHOLD, NOT A STATISTICAL ONE, and it must not be described as one. These
 * projections carry 80% ranges wide enough that a handful of rank places is well inside the noise
 * (`LEAGUE_DELTA_UNCERTAINTY` says so on the surface). This exists so the summary line counts
 * something a reader would recognise as movement rather than counting rounding.
 */
export const MEANINGFUL_MOVE = 5

/** How many risers/fallers the activation screen leads with. */
export const HIGHLIGHT_COUNT = 5

function rankable(p: Player): boolean {
  // A locked row (E9.56's retired redaction) carries no rank; a K/DST gap-fill row can carry a rank
  // with no points. Both would produce a meaningless delta, so neither enters the comparison.
  return p.ovrRank != null && p.pts != null
}

/**
 * Compare a league board against the free generic board.
 *
 * Returns `null` when either board is unavailable, so a caller renders a LOADING state rather than
 * an empty one — mirroring `useCustomBoard`'s null-until-ready contract. An empty delta and an
 * un-loaded delta are different facts and the screen states them differently.
 */
export function computeLeagueDelta(
  genericBoard: Player[] | undefined | null,
  leagueBoard: Player[] | undefined | null,
): LeagueDelta | null {
  if (!genericBoard?.length || !leagueBoard?.length) return null

  const generic = new Map<string, Player>()
  for (const p of genericBoard) {
    if (rankable(p)) generic.set(p.id, p)
  }

  const players: PlayerDelta[] = []
  for (const p of leagueBoard) {
    if (!rankable(p)) continue
    const g = generic.get(p.id)
    players.push({
      id: p.id,
      name: p.name,
      pos: p.pos,
      team: p.team,
      genericOvrRank: g?.ovrRank ?? null,
      genericPosRank: g?.posRank ?? null,
      genericVor: g?.vor ?? null,
      leagueOvrRank: p.ovrRank,
      leaguePosRank: p.posRank,
      leagueVor: p.vor ?? null,
      leaguePts: p.pts ?? null,
      // POSITIVE = moved UP. See the field docstring: rank is an inverted scale.
      ovrDelta: g ? g.ovrRank - p.ovrRank : null,
      posDelta: g ? g.posRank - p.posRank : null,
      vorDelta: g && g.vor != null && p.vor != null ? p.vor - g.vor : null,
      onlyInLeague: !g,
    })
  }

  const comparable = players.filter((d) => d.ovrDelta != null)
  // Sorted by SIZE of move, ties broken by the league rank so the order is deterministic — an
  // unstable order here would make the headline players change on every re-render.
  const byMove = comparable
    .slice()
    .sort(
      (a, b) =>
        Math.abs(b.ovrDelta as number) - Math.abs(a.ovrDelta as number) ||
        a.leagueOvrRank - b.leagueOvrRank,
    )

  const risers = comparable
    .filter((d) => (d.ovrDelta as number) > 0)
    .sort((a, b) => (b.ovrDelta as number) - (a.ovrDelta as number) || a.leagueOvrRank - b.leagueOvrRank)
    .slice(0, HIGHLIGHT_COUNT)

  const fallers = comparable
    .filter((d) => (d.ovrDelta as number) < 0)
    .sort((a, b) => (a.ovrDelta as number) - (b.ovrDelta as number) || a.leagueOvrRank - b.leagueOvrRank)
    .slice(0, HIGHLIGHT_COUNT)

  return {
    players: byMove,
    risers,
    fallers,
    positions: [],
    meaningfulMoves: comparable.filter((d) => Math.abs(d.ovrDelta as number) >= MEANINGFUL_MOVE)
      .length,
    compared: comparable.length,
  }
}

/**
 * Per-position replacement-level shift — the MECHANISM behind the player moves above.
 *
 * ⭐ THIS IS THE HALF THAT MAKES THE SCREEN EXPLANATORY RATHER THAN ASSERTIVE. "Kyle Pitts moved up
 * 18 places" is a fact the reader has to take on trust; "your league starts two tight ends, so TE
 * replacement level sits 31 points lower" is the reason, and it is arithmetic on settings they
 * typed in themselves. Surfaced, not asserted.
 *
 * ⚠️ REPLACEMENT LEVEL IS READ FROM THE ROWS, not from `BuiltBoard.replacement`, and deliberately:
 * the free board arrives as a bare `Player[]` from the pre-exported blob and has no such map, so a
 * `BuiltBoard`-only path would work for the league side and silently produce nulls for the generic
 * one. Every row carries its own `repl`, on both boards, which is the one field both shapes share.
 */
export function computePositionShifts(
  genericBoard: Player[] | undefined | null,
  leagueBoard: Player[] | undefined | null,
  positions: readonly string[],
): PositionShift[] {
  if (!genericBoard?.length || !leagueBoard?.length) return []

  const replacementFor = (board: Player[], pos: string): number | null => {
    for (const p of board) {
      if (p.pos === pos && p.repl != null) return p.repl
    }
    return null
  }
  const startableFor = (board: Player[], pos: string, repl: number | null): number | null => {
    if (repl == null) return null
    return board.filter((p) => p.pos === pos && p.pts != null && (p.pts as number) > repl).length
  }

  const out: PositionShift[] = []
  for (const pos of positions) {
    const g = replacementFor(genericBoard, pos)
    const l = replacementFor(leagueBoard, pos)
    // A position the league does not roster at all is absent from its board — skip it rather than
    // rendering a row of dashes that reads like missing data.
    if (l == null) continue
    out.push({
      pos,
      genericReplacement: g,
      leagueReplacement: l,
      replacementDelta: g == null ? null : l - g,
      genericStartable: startableFor(genericBoard, pos, g),
      leagueStartable: startableFor(leagueBoard, pos, l),
    })
  }
  return out
}
