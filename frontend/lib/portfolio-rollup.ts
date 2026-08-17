// NF-C6b — the cross-league portfolio rollup: a per-team projected starting-points total, and the
// ranked glance across every league.
//
// ⛔ NOTHING HERE SCORES ANYTHING. Every `pts` summed below was computed on the SERVER, on that
// league's OWN board (`app/backend/services/league_scoring.py` → `build_board(players, record)`,
// one call per league) and arrives on the rows `/fantasy/nfl/my-teams` already returns. This module
// adds arithmetic over numbers the page is holding, and nothing else.
//
// ⛔ AND DO NOT ADD A PER-CARD `/fantasy/nfl/league-board` FAN-OUT TO "GET THE SCORING". That
// inference — from a comment in `my-teams.tsx` that had been stale since NF-EPIC 1 — is exactly
// what mis-scoped NF-C6. The scores are already here; a fan-out would be N redundant round trips.
//
// ⭐ THE BAND MATH IS IMPORTED, NOT RE-SPELLED. `combineInterval` is NF-C6P2's, and a second copy
// would drift — the symptom being the roster report and this rollup disagreeing about the same
// team with neither looking wrong (E9.61).

import type { MyTeamEntry } from "@/lib/fantasy-queries"
import { combineInterval } from "@/lib/roster-report"
import type { RosterMatch } from "@/lib/league-scoring"

export interface TeamRollup {
  leagueId: string
  leagueName: string
  /** The league's own format, carried WITH the total. A points total is meaningless without the
   *  rules that produced it, and these totals come from different rule sets (see `PortfolioRollup`). */
  formatLabel: string
  teamName: string | null
  /** Σ of the starters' league-scored season projections. EXACT under any dependence between
   *  players — expectation is linear, which is why the total needs no independence assumption even
   *  though the BAND below does. */
  total: number
  /** The 80% band, combining the starters' own bands as INDEPENDENT (`combineInterval`). */
  p10: number | null
  p90: number | null
  /** The same band if every season moved together — the widest admissible reading. Carried so the
   *  independence assumption is BOUNDED rather than merely disclosed (NF-W7b: independent draws
   *  under-disperse a correlated sum, and a fantasy roster co-moves for obvious reasons). */
  correlatedP10: number | null
  correlatedP90: number | null
  /** Starters we could score, and starters we could not. */
  starters: number
  /** ⭐ Starters with no matched projection. Their points are NOT in `total`, so the total is
   *  UNDERSTATED by whatever they are worth — a fact the surface must state rather than quietly
   *  ranking a short team against a complete one. */
  unscoredStarters: number
  /** Competition rank on the total (1 = highest). Ties share a rank. */
  rank: number
}

export interface PortfolioRollup {
  teams: TeamRollup[]
  /** At least one total is understated by an unscored starter — so the ORDER may be wrong, not just
   *  the magnitudes, and the surface says so. */
  anyUnderstated: boolean
  /** The leagues in this rollup do not all share a scoring format. ⚠️ When true, ranking by raw
   *  points is NOT a roster-strength comparison: a half-PPR team out-totals an identical standard
   *  roster purely because its league pays for receptions. The surface must say this unconditionally
   *  — it is the single most misreadable thing about a cross-league ranking. */
  mixedFormats: boolean
}

/** Human-readable scoring format for a saved league ("half ppr", "standard", "+ superflex"). */
function formatLabelFor(league: MyTeamEntry["league"]): string {
  const ppr = String(league.ppr ?? "").replace(/_/g, " ").trim() || "custom"
  return league.superflex ? `${ppr} · superflex` : ppr
}

/** The rows the page shows under "Starters" — the PLATFORM's own lineup, which is what My Teams
 *  renders. ⚠️ Deliberately NOT `fillLineup`: the roster report constructs OUR optimizer's best
 *  lineup, a different (and larger) number. Using it here would print a total that does not equal
 *  the Starters table sitting directly beneath it, which the reader would rightly read as a bug. */
const startersOf = (roster: RosterMatch[]): RosterMatch[] => roster.filter((r) => r.roster.starter)

/**
 * One team's rollup, or `null` when there is nothing to total.
 *
 * `null` covers two honest states that are NOT failures and must not render as a zero: a league
 * with no team linked, and a linked team whose platform lineup names no starters (pre-draft, or a
 * platform that reported a roster without lineup flags). ⛔ A `0.0` total for either would be a
 * fabricated number — the reader cannot tell "we totalled nothing" from "your starters are worth
 * nothing", and the second is a claim we never made.
 */
export function teamRollup(entry: MyTeamEntry): TeamRollup | null {
  const starters = startersOf(entry.roster ?? [])
  if (starters.length === 0) return null

  // Built by narrowing rather than by asserting: a starter counts only once its board row and its
  // `pts` are both genuinely present, and anything else lands in `unscoredStarters` and is disclosed.
  const rows: { pts: number; p10: number | null; p90: number | null }[] = []
  for (const r of starters) {
    const pts = r.board?.pts
    if (pts == null || !Number.isFinite(pts)) continue
    rows.push({ pts, p10: r.board?.ptsP10 ?? null, p90: r.board?.ptsP90 ?? null })
  }
  if (rows.length === 0) return null

  const band = combineInterval(rows)

  return {
    leagueId: entry.league.league_id,
    leagueName: entry.league.name,
    formatLabel: formatLabelFor(entry.league),
    teamName: entry.league.source_team_name ?? null,
    total: rows.reduce((n, r) => n + r.pts, 0),
    p10: band.p10,
    p90: band.p90,
    correlatedP10: band.correlatedP10,
    correlatedP90: band.correlatedP90,
    starters: rows.length,
    unscoredStarters: starters.length - rows.length,
    rank: 0,
  }
}

/**
 * Every team that has a total, ranked.
 *
 * Returns `null` below two teams. A "ranking" of one team is not a ranking, and rendering it would
 * dress a single number up as a comparison — the same reason `leagueComparison` refuses a one-row
 * table. The per-team total still renders on that league's own card.
 */
export function portfolioRollup(entries: MyTeamEntry[] | null | undefined): PortfolioRollup | null {
  const rollups = (entries ?? [])
    .map(teamRollup)
    .filter((t): t is TeamRollup => t != null)
  if (rollups.length < 2) return null

  // Sorted by total, then by league NAME — so a tie breaks deterministically rather than by
  // whatever order the server happened to serve the leagues in.
  const sorted = rollups
    .slice()
    .sort((a, b) => b.total - a.total || a.leagueName.localeCompare(b.leagueName))

  // ⭐ COMPETITION RANKING ON THE TOTAL AS RENDERED (one decimal). Two teams showing the same number
  // must not carry different ranks — that is a distinction the reader cannot see and which does not
  // exist in the data. Same convention as `leagueComparison`.
  let rank = 0
  let previous: number | null = null
  sorted.forEach((row, i) => {
    const shown = Math.round(row.total * 10) / 10
    if (previous == null || shown !== previous) rank = i + 1
    previous = shown
    row.rank = rank
  })

  return {
    teams: sorted,
    anyUnderstated: sorted.some((t) => t.unscoredStarters > 0),
    mixedFormats: new Set(sorted.map((t) => t.formatLabel)).size > 1,
  }
}
