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
  /** Market average draft position, from whichever board carries one for him. A REFERENCE used
   *  ONLY to decide whether he is realistically drafted — never an input to any ranking. */
  adp: number | null
  /** Inside this league's draft pool — see `isDraftable`. Every player still appears on the board;
   *  this only decides who is eligible to be a HIGHLIGHT. */
  draftable: boolean
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
  /** How many DRAFTABLE players moved at least `MEANINGFUL_MOVE` places overall — the one-line
   *  summary. Pool-scoped for the same reason the highlights are (see `draftablePoolSize`). */
  meaningfulMoves: number
  /** Draftable players compared on both boards. The denominator, so "14 of 180 moved" is readable
   *  AND is a sentence about players the reader might actually draft. */
  compared: number
  /** The pool the two numbers above are scoped to, or null when it could not be computed (then
   *  nothing is filtered and these are whole-board counts). Rendered, so the scope is stated. */
  poolSize: number | null
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

// ══ THE DRAFTABLE POOL ═══════════════════════════════════════════════════════════════════════════
//
// ⭐ WHY THIS EXISTS (operator, live on the first real league). The first cut ranked highlights by
// raw overall-rank movement across the WHOLE board, and every riser and faller it produced was a
// player nobody would draft in any league. That is not a tuning miss, it is STRUCTURAL: rank density
// grows down the board. Around pick 30 a few points of projection separates adjacent players; around
// rank 400 the same few points spans dozens of them. So the largest RANK moves live in the deep tail
// by construction, and a highlight list sorted by rank movement is a list of waiver-wire churn —
// arithmetically correct, and useless on the one screen the funnel converts on.
//
// The fix is a POPULATION, not a different sort: compare everyone, but only let a player who might
// actually be drafted in THIS league be the headline.
//
// ⚠️ THE POOL IS A LEAGUE PROPERTY, WHICH IS THE POINT. `n_teams × drafted slots` is 180 in a
// 12-team/15-round league and 100 in a 10-team/10-round one, so the same board yields a different
// (correct) highlight set per league. A hardcoded "top 200" would be a different, wrong answer for
// most leagues and would silently stop scaling the moment someone imports a 14-team dynasty.

/** Roster slots that are NOT filled from the draft. All three import adapters normalise to these
 *  exact names (`espn.py` / `yahoo.py` / `sleeper.py` ROSTER_SLOT_MAPs), and the manual editor
 *  offers no such slot, so a name match is reliable across every path a config can arrive by. */
const NON_DRAFT_SLOTS = new Set(["IR", "TAXI"])

/** Shape needed to size the pool — a structural subset of `LeagueConfig`, so this module keeps
 *  taking plain data and does not have to import the config types. */
export interface PoolShape {
  n_teams?: number | null
  roster?: { name?: string | null; count?: number | null }[] | null
}

/**
 * How many players get drafted in this league: teams × roster slots, EXCLUDING IR and taxi.
 *
 * Bench slots are deliberately INCLUDED — bench spots are filled in the draft, and a player taken
 * in the last round is exactly the kind of "does my scoring make him worth a pick?" call this screen
 * should be able to speak to. IR and taxi are excluded because they are filled after it.
 *
 * Returns null when the config cannot answer (no teams, no roster) rather than guessing a default:
 * an invented pool would silently filter a real board against a made-up number.
 */
export function draftablePoolSize(config: PoolShape | null | undefined): number | null {
  const teams = Number(config?.n_teams ?? 0)
  const slots = draftedSlotsPerTeam(config)
  if (!Number.isFinite(teams) || teams <= 0 || slots == null) return null
  return Math.round(teams * slots)
}

/** Drafted roster spots per team — the other half of the pool, exported so the screen can SHOW the
 *  arithmetic ("12 teams × 15 spots") instead of dividing the product back out, which would be a
 *  second, silently-derived definition of the same number. */
export function draftedSlotsPerTeam(config: PoolShape | null | undefined): number | null {
  const slots = (config?.roster ?? []).reduce((n, s) => {
    if (NON_DRAFT_SLOTS.has(String(s?.name ?? "").toUpperCase())) return n
    const c = Number(s?.count ?? 0)
    return n + (Number.isFinite(c) && c > 0 ? c : 0)
  }, 0)
  return slots > 0 ? slots : null
}

/**
 * Is this player realistically drafted in a league of this size?
 *
 * TWO independent reasons to say yes, OR'd — and the OR is load-bearing in both directions:
 *
 *  • MARKET: his ADP is inside the pool. The market is the authority on who actually gets drafted,
 *    and deferring to it here is the opposite of a claim against it — we are using ADP to bound OUR
 *    list, never to say we beat it. ⛔ Nothing downstream may present this as an ADP comparison.
 *  • THIS LEAGUE'S BOARD: he is inside the pool on the board the reader is about to use. Required,
 *    because ADP is sampled in ONE format: a superflex QB, a rookie with no sample, and every player
 *    on a board exported before ADP existed all have `adp == null`, and judging them by the market
 *    alone would delete exactly the players whose value this league CREATES — the most interesting
 *    highlights on the page.
 *
 * A null pool means "unknown", and unknown must not filter: everyone stays eligible.
 */
export function isDraftable(
  adp: number | null,
  leagueOvrRank: number,
  pool: number | null,
): boolean {
  if (pool == null) return true
  if (adp != null && adp <= pool) return true
  return leagueOvrRank <= pool
}

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
  pool: number | null = null,
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
    // Either board's ADP will do — it is the same market sample, and the league board inherits it
    // from the projections row (`league-scoring.buildBoard`). Taking the league side first keeps a
    // format-matched value when one exists.
    const adp = p.adp ?? g?.adp ?? null
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
      adp,
      draftable: isDraftable(adp, p.ovrRank, pool),
    })
  }

  // ⚠️ THE POOL FILTER APPLIES TO THE HIGHLIGHTS AND THE SUMMARY, NEVER TO `players`. That array
  // feeds the board's "vs free board" column for EVERY row, so filtering it here would blank the
  // column for most of the table — hiding a real number rather than declining to headline it. A
  // deep-tail move is still shown where the reader is looking at that player; it just cannot be the
  // headline. `allComparable` is therefore the full set and `comparable` the pool-scoped one.
  const allComparable = players.filter((d) => d.ovrDelta != null)
  const comparable = allComparable.filter((d) => d.draftable)

  // Sorted by SIZE of move, ties broken by the league rank so the order is deterministic — an
  // unstable order here would make the headline players change on every re-render.
  const byMove = allComparable
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
    poolSize: pool,
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
