// NF-C6b — the cross-league portfolio rollup: two totals per team, the gap between them, and the
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
// ⭐ THE LINEUP MATH IS IMPORTED, NOT RE-SPELLED. `fillLineup` and `combineInterval` are NF-C6P2's,
// and a second copy would drift — the symptom being the roster report and this rollup disagreeing
// about the same team with neither looking wrong (E9.61).
//
// ══ WHY THERE ARE TWO TOTALS, AND WHY THE GAP IS THE POINT ══════════════════════════════════════
//
// AS-SET sums the starters the PLATFORM reported. It is checkable — it equals the Starters table
// rendered directly beneath it — and it is "your team as it stands".
//
// BEST-POSSIBLE sums OUR optimizer's best legal lineup from the whole roster. It is what the roster
// is worth if the lineup were right.
//
// ⭐ RANKING USES BEST-POSSIBLE. Ranking on as-set pre-kickoff would partly rank LINEUP-SETTING
// DILIGENCE rather than roster strength: most platform lineups this side of Week 1 are whatever was
// auto-assigned at the draft, so a team whose owner has not touched it would place low for a reason
// that says nothing about the roster.
//
// ⭐ AND THE GAP IS THE ONE FIGURE HERE WITH NO CROSS-LEAGUE CONFOUND. Both totals come from the
// SAME league's scoring, so their difference is immune to the scoring-format problem that makes the
// cross-league ranking only a rough guide — which is why the surface leads on it.

import type { MyTeamEntry } from "@/lib/fantasy-queries"
import { combineInterval, fillLineup, toReportPlayers } from "@/lib/roster-report"
import type { RosterMatch } from "@/lib/league-scoring"

/** Below this the two lineups are the same lineup, and "leaving 0.0 points on your bench" is noise.
 *  Points render to one decimal, so anything under half a tick is a rounding artefact. */
export const GAP_EPSILON = 0.05

export interface TeamRollup {
  leagueId: string
  leagueName: string
  /** The league's own format, carried WITH the totals. A points total is meaningless without the
   *  rules that produced it, and these totals come from different rule sets (see `PortfolioRollup`). */
  formatLabel: string
  teamName: string | null
  /** Σ of the starters the PLATFORM reported — equal to the card's own Starters table. */
  asSet: number
  /** Σ of OUR optimizer's best legal lineup from the whole roster. */
  bestPossible: number
  /** `bestPossible − asSet`: what the current lineup is leaving on the bench.
   *  ⚠️ CAN BE ≤ 0. A platform that reports more starters than the league has startable slots (or a
   *  slot model of ours that disagrees with theirs) makes as-set the larger number. That is not
   *  "negative points on your bench" — the surface renders it as "already your best lineup" rather
   *  than printing a negative, and never claims we would improve on it. */
  gap: number
  /** The 80% band on BEST-POSSIBLE, combining its starters' own bands as INDEPENDENT
   *  (`combineInterval`). */
  p10: number | null
  p90: number | null
  /** The same band if every season moved together — the widest admissible reading. Carried so the
   *  independence assumption is BOUNDED rather than merely disclosed (NF-W7b: independent draws
   *  under-disperse a correlated sum, and a fantasy roster co-moves for obvious reasons). */
  correlatedP10: number | null
  correlatedP90: number | null
  /** Platform starters we could score, and platform starters we could not. */
  starters: number
  /** ⭐ Starters with no matched projection. Their points are NOT in `asSet`, so it is UNDERSTATED
   *  by whatever they are worth — a fact the surface states rather than quietly ranking a short team
   *  against a complete one. */
  unscoredStarters: number
  /** Starting slots the roster cannot fill at all, so BEST-POSSIBLE is a total over a PARTIAL
   *  lineup. A four-player roster's "best possible lineup" is not a lineup, and saying so is the
   *  difference between a small number and a wrong one. */
  unfilledSlots: number
  /** Competition rank on BEST-POSSIBLE (1 = highest). Ties share a rank. */
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

/** The rows the page shows under "Starters" — the PLATFORM's own lineup. */
const startersOf = (roster: RosterMatch[]): RosterMatch[] => roster.filter((r) => r.roster.starter)

/**
 * One team's rollup, or `null` when there is nothing to total.
 *
 * `null` covers two honest states that are NOT failures and must not render as a zero: a league
 * with no team linked, and a linked team whose platform lineup names no scoreable starters. ⛔ A
 * `0.0` total for either would be a fabricated number — the reader cannot tell "we totalled
 * nothing" from "your starters are worth nothing", and the second is a claim we never made.
 */
export function teamRollup(entry: MyTeamEntry): TeamRollup | null {
  const roster = entry.roster ?? []
  const starters = startersOf(roster)
  if (starters.length === 0) return null

  // AS-SET. Built by narrowing rather than by asserting: a starter counts only once its board row
  // and its `pts` are both genuinely present, and anything else lands in `unscoredStarters`.
  const setRows: { pts: number; p10: number | null; p90: number | null }[] = []
  for (const r of starters) {
    const pts = r.board?.pts
    if (pts == null || !Number.isFinite(pts)) continue
    setRows.push({ pts, p10: r.board?.ptsP10 ?? null, p90: r.board?.ptsP90 ?? null })
  }
  if (setRows.length === 0) return null
  const asSet = setRows.reduce((n, r) => n + r.pts, 0)

  // BEST-POSSIBLE, over the WHOLE roster (bench included) through the same most-restrictive-slot-
  // first fill the roster report uses for every team it compares.
  const { players } = toReportPlayers(roster)
  const lineup = fillLineup(players, entry.league.roster ?? [], (p) => p.pts)
  const fielded = lineup.slots.map((s) => s.player).filter((p): p is NonNullable<typeof p> => p != null)
  const band = combineInterval(fielded.map((p) => ({ pts: p.pts, p10: p.p10, p90: p.p90 })))

  return {
    leagueId: entry.league.league_id,
    leagueName: entry.league.name,
    formatLabel: formatLabelFor(entry.league),
    teamName: entry.league.source_team_name ?? null,
    asSet,
    bestPossible: lineup.total,
    gap: lineup.total - asSet,
    p10: band.p10,
    p90: band.p90,
    correlatedP10: band.correlatedP10,
    correlatedP90: band.correlatedP90,
    starters: setRows.length,
    unscoredStarters: starters.length - setRows.length,
    unfilledSlots: lineup.unfilled,
    rank: 0,
  }
}

/**
 * Every team that has a total, ranked by BEST-POSSIBLE.
 *
 * Returns `null` below two teams. A "ranking" of one team is not a ranking, and rendering it would
 * dress a single number up as a comparison — the same reason `leagueComparison` refuses a one-row
 * table. The per-team totals still render on that league's own card.
 */
export function portfolioRollup(entries: MyTeamEntry[] | null | undefined): PortfolioRollup | null {
  const rollups = (entries ?? []).map(teamRollup).filter((t): t is TeamRollup => t != null)
  if (rollups.length < 2) return null

  // ⭐ ORDERED ON BEST-POSSIBLE, not on as-set — see this module's header. Ties break by league NAME
  // so the order is deterministic rather than however the server happened to serve the leagues.
  const sorted = rollups
    .slice()
    .sort((a, b) => b.bestPossible - a.bestPossible || a.leagueName.localeCompare(b.leagueName))

  // ⭐ COMPETITION RANKING ON THE FIGURE AS RENDERED (one decimal). Two teams showing the same
  // number must not carry different ranks — that is a distinction the reader cannot see and which
  // does not exist in the data. Same convention as `leagueComparison`.
  let rank = 0
  let previous: number | null = null
  sorted.forEach((row, i) => {
    const shown = Math.round(row.bestPossible * 10) / 10
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
