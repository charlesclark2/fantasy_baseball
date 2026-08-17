"use client"

// NF-C6 Phase 1 — My Teams: a cross-league browse surface, one place to see every imported team's
// roster scored under ITS OWN league's format.
//
// Composes what already exists: NF-C0's saved leagues + NF-C0c's roster name resolution. No new
// model, no new scoring logic.
//
// ⚠️ THIS HEADER USED TO SAY THE SCORING HAPPENS HERE, IN THE BROWSER, VIA `buildBoard` — AND THAT
// IT "CANNOT MOVE SERVER-SIDE". Both halves stopped being true at NF-EPIC 1 (`144fa808`), which
// made the raw stat line paid, ported the scorer to `app/backend/services/league_scoring.py` and
// moved the arithmetic there. This file was not updated with it, so the comment sat here asserting
// the opposite of what the code does — and a false comment is worse than a false doc, because the
// next reader takes it as the design (a stale doc costs a lookup; this one drives a rewrite).
//
// WHAT ACTUALLY HAPPENS: `/fantasy/nfl/my-teams` returns each league's roster ALREADY JOINED to a
// board scored under THAT league's own config (`_scored_rosters` → `build_board(players, record)`,
// one `build_board` per league). This component renders `RosterMatch.board` and does no arithmetic.
//
// ⛔ SO DO NOT ADD A PER-CARD `/fantasy/nfl/league-board` FAN-OUT TO "GET THE SCORING". The scores
// are already on the rows this page receives; a fan-out would be N redundant round trips for numbers
// it already has. What `/my-teams` omits is the FULL ~858-row BOARD (25 leagues × that is ~6 MB,
// past Lambda's proxy-response cap) — not the roster's scores. `useMyTeams` sets `board: null` for
// that reason alone; a page needing one league's whole board calls `useLeagueBoard`.
//
// ROS = the season projection (pre-kickoff, so "rest of season" is effectively the full season) —
// labelled honestly, never faked into a per-game number (a per-game figure divided out of a season
// total is false precision). Per-game splits, weekly rest-of-season updates and waiver-wire
// suggestions are PHASE 2, gated on the NF-W1 weekly model — stubbed below as "coming in-season,"
// not built or faked here.

import Link from "next/link"
import { useMyTeams } from "@/lib/fantasy-queries"
import type { MyTeamEntry } from "@/lib/fantasy-queries"
import {
  EmptyBlock,
  GLOSSARY,
  InfoTip,
  LoadingBlock,
  PosBadge,
  RangeCell,
  SurfaceHeader,
  num,
} from "@/components/fantasy/shared"
import {
  EXPECTED_POINTS_LABEL,
  PORTFOLIO_AS_SET_LABEL,
  PORTFOLIO_BEST_LABEL,
  PORTFOLIO_CAVEAT_FORMATS,
  PORTFOLIO_CAVEAT_LINEUP,
  PORTFOLIO_CAVEAT_SNAPSHOT,
  PORTFOLIO_GAP_LABEL,
  PORTFOLIO_GAP_NONE,
  PORTFOLIO_GAP_NOTE,
  PORTFOLIO_HEADING,
  PORTFOLIO_NOTE,
  PORTFOLIO_TOTAL_LABEL,
  PORTFOLIO_UNDERSTATED_NOTE,
  portfolioGapHeadline,
  portfolioUnfilledNote,
  portfolioUnscoredNote,
  UNMATCHED_DETAIL,
  UNMATCHED_LABEL,
  unmatchedFootnote,
  type UnmatchedCause,
} from "@/lib/fantasy-claim-copy"
import type { RosterMatch } from "@/lib/league-scoring"
import { classifyUnmatched } from "@/lib/league-scoring"
import { GAP_EPSILON, portfolioRollup, teamRollup, type TeamRollup } from "@/lib/portfolio-rollup"

export function MyTeams() {
  const { teams, isLoading, isError, boardPositions } = useMyTeams()

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <SurfaceHeader
        title="My Teams"
        blurb="Every league you've imported, in one place — each roster scored under that league's own format, and every team totalled and ranked. Projections are the rest-of-season figure (pre-kickoff, so this is effectively the full season)."
      />

      {isError && (
        <EmptyBlock
          title="Could not load your teams"
          detail="Something went wrong reading your saved leagues. Try reloading the page."
        />
      )}

      {!isError && (isLoading || teams === null) && <LoadingBlock label="Loading your teams…" />}

      {!isError && teams !== null && teams.length === 0 && (
        <EmptyBlock
          title="No saved leagues yet"
          detail="Import a league from a platform, or enter one by hand, and it will show up here with your roster scored under its exact format."
        />
      )}

      {!isError && teams !== null && teams.length > 0 && (
        <div className="space-y-6">
          {/* NF-C6b — the aggregate glance, ABOVE the per-league detail. A portfolio's value is the
              comparison; burying it under N roster tables is the list this page already was. */}
          <PortfolioSummary teams={teams} />
          {teams.map((entry) => (
            <LeagueCard
              key={entry.league.league_id}
              entry={entry}
              boardPositions={boardPositions}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * NF-C6b — every team with a total, ranked.
 *
 * ⚠️ A `<div>`, DELIBERATELY, not a `<section>`. `fantasy-my-teams.spec.ts` locates a league card as
 * `page.locator("section").filter({ hasText: <league name> }).first()`, and this block names every
 * league — so as a `<section>` it would sit ABOVE the cards in the DOM and every existing card
 * assertion would silently rebind to this summary instead. The rendered result would look right and
 * the spec would be asserting about the wrong element.
 */
function PortfolioSummary({ teams }: { teams: MyTeamEntry[] }) {
  const rollup = portfolioRollup(teams)
  // Below two teams there is no ranking to show — the per-league card still carries its own total.
  if (!rollup) return null

  return (
    <div
      data-testid="portfolio-summary"
      className="rounded-lg border border-emerald-500/20 bg-emerald-500/[0.03] p-4"
    >
      <div className="text-base font-medium text-gray-100">{PORTFOLIO_HEADING}</div>
      <p className="mt-1 text-xs text-gray-400">{PORTFOLIO_NOTE}</p>

      {/* ⚠️ NO `min-w` HERE. A fixed minimum width forces the whole page to scroll sideways on a
          phone, which is exactly what a portfolio GLANCE must not do — the operator hit this on the
          roster tables below. The two lowest-value columns drop out under `sm` instead, so the
          ranked figure and the bench gap are always on screen. `overflow-x-auto` stays as a
          backstop for a very narrow device, never as the primary layout. */}
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-left text-[11px]">
          <thead>
            <tr className="text-gray-600">
              <th className="py-1 pr-2 font-medium">#</th>
              <th className="py-1 pr-2 font-medium">League</th>
              <th className="hidden py-1 pr-2 font-medium sm:table-cell">Scoring</th>
              {/* ⭐ BEST-POSSIBLE IS THE RANKED COLUMN and sits first of the three numbers, because
                  the order is only legible if the figure it was sorted on leads. */}
              <th className="py-1 pr-2 text-right font-medium">{PORTFOLIO_BEST_LABEL}</th>
              <th className="py-1 pr-2 text-right font-medium">{PORTFOLIO_AS_SET_LABEL}</th>
              <th className="py-1 pr-2 text-right font-medium">{PORTFOLIO_GAP_LABEL}</th>
              <th className="hidden py-1 pr-2 text-right font-medium sm:table-cell">80% range</th>
            </tr>
          </thead>
          <tbody>
            {rollup.teams.map((t) => (
              <tr key={t.leagueId} data-testid="portfolio-row" className="border-t border-white/5">
                <td className="py-1 pr-2 text-gray-500">{t.rank}</td>
                <td className="py-1 pr-2 text-gray-200">
                  {t.leagueName}
                  {t.teamName && <span className="text-gray-500"> · {t.teamName}</span>}
                </td>
                <td className="hidden py-1 pr-2 text-gray-500 sm:table-cell">{t.formatLabel}</td>
                <td
                  className="py-1 pr-2 text-right font-medium text-gray-100"
                  data-testid="portfolio-best"
                >
                  {num(t.bestPossible)}
                </td>
                <td className="py-1 pr-2 text-right text-gray-400" data-testid="portfolio-as-set">
                  {num(t.asSet)}
                  {t.unscoredStarters > 0 && (
                    <span className="text-amber-400" title={portfolioUnscoredNote(t.unscoredStarters)}>
                      {" "}
                      +{t.unscoredStarters}?
                    </span>
                  )}
                </td>
                <td
                  className={`py-1 pr-2 text-right ${
                    t.gap >= GAP_EPSILON ? "font-medium text-emerald-300" : "text-gray-600"
                  }`}
                  data-testid="portfolio-gap"
                >
                  {t.gap >= GAP_EPSILON ? `+${num(t.gap)}` : "—"}
                </td>
                <td className="hidden py-1 pr-2 text-right sm:table-cell">
                  <RangeCell p10={t.p10} p90={t.p90} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ⭐ THE CAVEATS RENDER WITH THE TABLE, never behind a disclosure — a caveat behind a click is
          a caveat that did not render (NF-C6P3's own finding). */}
      <ul className="mt-3 space-y-1 text-[11px] text-gray-500">
        {rollup.mixedFormats && <li>{PORTFOLIO_CAVEAT_FORMATS}</li>}
        <li>{PORTFOLIO_CAVEAT_LINEUP}</li>
        <li>{PORTFOLIO_CAVEAT_SNAPSHOT}</li>
        {rollup.anyUnderstated && <li className="text-amber-400/80">{PORTFOLIO_UNDERSTATED_NOTE}</li>}
      </ul>
    </div>
  )
}

/**
 * NF-C6b — one team's two totals and the gap between them. Rendered even when there is no ranking
 * (a single league still has meaningful totals), which is why this is separate from
 * `PortfolioSummary`.
 *
 * ⭐ THE GAP LEADS. It is the only figure on this surface with no cross-league confound — both
 * totals come from the SAME league's scoring, so their difference is unaffected by the scoring and
 * roster-size differences that keep the ranking a rough guide — and it is the one number here a
 * reader can act on.
 */
function TeamTotal({ rollup }: { rollup: TeamRollup }) {
  const hasGap = rollup.gap >= GAP_EPSILON
  return (
    <div
      data-testid="team-total"
      className="mt-3 rounded border border-white/10 bg-white/[0.02] px-3 py-2"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="text-[11px] text-gray-500">
          {PORTFOLIO_BEST_LABEL}
          <span className="ml-2 text-sm font-medium text-gray-100" data-testid="team-best-value">
            {num(rollup.bestPossible)}
          </span>
          <span className="ml-2 text-gray-500">
            <RangeCell p10={rollup.p10} p90={rollup.p90} />
          </span>
        </div>
        <div className="text-[11px] text-gray-500">
          {PORTFOLIO_AS_SET_LABEL}
          <span className="ml-2 text-sm text-gray-300" data-testid="team-as-set-value">
            {num(rollup.asSet)}
          </span>
        </div>
      </div>

      {/* ⭐ THE HERO LINE — prominent, not a footnote. */}
      <p
        className={`mt-2 text-xs font-medium ${hasGap ? "text-emerald-300" : "text-gray-500"}`}
        data-testid="team-gap"
        title={PORTFOLIO_GAP_NOTE}
      >
        {hasGap ? portfolioGapHeadline(num(rollup.gap)) : PORTFOLIO_GAP_NONE}
      </p>
      <p className="mt-1 text-[11px] text-gray-600">{PORTFOLIO_TOTAL_LABEL}</p>

      {rollup.unscoredStarters > 0 && (
        <p className="mt-1 text-[11px] text-amber-400/80">
          {portfolioUnscoredNote(rollup.unscoredStarters)}
        </p>
      )}
      {rollup.unfilledSlots > 0 && (
        <p className="mt-1 text-[11px] text-gray-600">
          {portfolioUnfilledNote(rollup.unfilledSlots)}
        </p>
      )}
    </div>
  )
}

function LeagueCard({
  entry,
  boardPositions,
}: {
  entry: MyTeamEntry
  boardPositions: string[] | null
}) {
  const { league, roster } = entry
  // NF-C6 fix: "linked" and "has any rostered players" are DIFFERENT states, and conflating them
  // produced a genuinely wrong message — a pre-draft league (ESPN/Sleeper both warn about this at
  // import time) has a real, saved `source_team_key` with a legitimately EMPTY roster, which is not
  // the same as "you never picked a team." `roster.length` alone can't tell those apart.
  const linked = !!league.source_team_key
  const hasPlayers = roster.length > 0
  const matchedCount = roster.filter((r) => r.board).length
  const unmatchedCount = roster.length - matchedCount
  const starters = roster.filter((r) => r.roster.starter)
  const bench = roster.filter((r) => !r.roster.starter)
  // NF-C6b — `null` when this team has no scoreable starters, which is a real state (pre-draft, or a
  // platform that reported no lineup) and must not render as a fabricated 0.0.
  const rollup = teamRollup(entry)

  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.02] p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <div className="text-base font-medium text-gray-100">{league.name}</div>
          <div className="mt-0.5 text-xs text-gray-500">
            {league.n_teams}-team · {league.ppr.replace(/_/g, " ")}
            {league.superflex ? " · superflex" : ""}
            {league.source_team_name ? ` · ${league.source_team_name}` : ""}
          </div>
        </div>
        {league.roster_synced_at && (
          <div className="text-[11px] text-gray-600" title={league.roster_synced_at}>
            Roster as of {new Date(league.roster_synced_at).toLocaleDateString()}
          </div>
        )}
      </div>

      {!linked && (
        <p className="mt-3 text-xs text-gray-500">
          No team linked yet.{" "}
          <Link href="/fantasy/import" className="text-emerald-400 hover:underline">
            Re-import this league
          </Link>{" "}
          and pick your team to see your roster&rsquo;s projection here.
        </p>
      )}

      {linked && !hasPlayers && (
        <p className="mt-3 text-xs text-gray-500">
          {league.source_team_name ? `${league.source_team_name} is` : "Your team is"}{" "}
          linked, but the platform reported no rostered players for it — the usual reason is your
          league hasn&rsquo;t drafted yet. Re-import after your draft and the roster will show up
          here.
        </p>
      )}

      {linked && hasPlayers && (
        <>
          {rollup && <TeamTotal rollup={rollup} />}
          <RosterTable label="Starters" rows={starters} boardPositions={boardPositions} />
          <RosterTable label="Bench" rows={bench} boardPositions={boardPositions} />
          {unmatchedCount > 0 && (
            // NF-K1 — the footnote now NAMES the cause (and the positions), instead of the one
            // sentence that read as a name-resolution failure for every unmatched row.
            <p className="mt-2 text-[11px] text-gray-600" data-testid="unmatched-footnote">
              {unmatchedFootnote(matchedCount, roster.length, unmatchedCauses(roster, boardPositions))}
            </p>
          )}
          <p className="mt-3 text-[11px] text-gray-600">
            Per-game splits, weekly rest-of-season updates and waiver-wire suggestions are coming
            in-season, once the weekly model ships — this page shows the season/ROS projection only.
          </p>
        </>
      )}
    </section>
  )
}

/**
 * NF-K1 — the distinct causes present on ONE roster, each with the positions it applies to, in a
 * stable order so the footnote reads the same way twice.
 *
 * ⚠️ Built from the SAME `classifyUnmatched` the table cells call. A footnote that counted causes
 * its own way would be free to disagree with the cells right above it (E9.61).
 */
function unmatchedCauses(
  roster: RosterMatch[],
  boardPositions: string[] | null,
): { cause: UnmatchedCause; positions: string[] }[] {
  const order: UnmatchedCause[] = ["not-published", "unresolved", "not-projected", "unknown"]
  const byCause = new Map<UnmatchedCause, Set<string>>()
  for (const r of roster) {
    if (r.board) continue
    const cause = classifyUnmatched(r.roster.position, boardPositions)
    const set = byCause.get(cause) ?? new Set<string>()
    if (r.roster.position) set.add(r.roster.position)
    byCause.set(cause, set)
  }
  return order
    .filter((c) => byCause.has(c))
    .map((cause) => ({ cause, positions: [...(byCause.get(cause) ?? [])].sort() }))
}

function RosterTable({
  label,
  rows,
  boardPositions,
}: {
  label: string
  rows: RosterMatch[]
  boardPositions: string[] | null
}) {
  if (rows.length === 0) return null
  return (
    // NF-C6b — a stable hook so the rollup gate can sum THIS table rather than traversing the card's
    // DOM shape. The team total's contract is "Σ of the rows in Starters", and a spec that located
    // the wrong table would still find numbers and still add up to something.
    <div className="mt-4" data-testid={`${label.toLowerCase()}-table`}>
      <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
        {label} · {rows.length}
      </div>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-left text-[11px]">
          <thead>
            <tr className="text-gray-600">
              <th className="py-1 pr-2 font-medium">Player</th>
              <th className="py-1 pr-2 font-medium">Pos</th>
              <th className="hidden py-1 pr-2 font-medium sm:table-cell">Team</th>
              <th className="py-1 pr-2 text-right font-medium">
                <InfoTip label={`${EXPECTED_POINTS_LABEL} (ROS)`}>{GLOSSARY.expectedPoints}</InfoTip>
              </th>
              <th className="hidden py-1 pr-2 text-right font-medium sm:table-cell">80% range</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.roster.player_key} className="border-t border-white/5">
                <td className="py-1 pr-2 text-gray-200">
                  {r.roster.name || `#${r.roster.player_key}`}
                </td>
                <td className="py-1 pr-2">
                  {r.roster.position ? (
                    <PosBadge pos={r.roster.position} />
                  ) : (
                    <span className="text-gray-600">—</span>
                  )}
                </td>
                <td className="hidden py-1 pr-2 text-gray-500 sm:table-cell">
                  {r.roster.team ?? "—"}
                </td>
                <td className="py-1 pr-2 text-right text-gray-200">
                  {r.board ? (
                    num(r.board.pts)
                  ) : (
                    // NF-K1 — the cell says WHICH of the three reasons applies. The full sentence
                    // is the title, so the cause is available on hover as well as in the footnote.
                    <span
                      className="text-gray-600"
                      data-testid="unmatched-cell"
                      data-cause={classifyUnmatched(r.roster.position, boardPositions)}
                      title={UNMATCHED_DETAIL[classifyUnmatched(r.roster.position, boardPositions)]}
                    >
                      {UNMATCHED_LABEL[classifyUnmatched(r.roster.position, boardPositions)]}
                    </span>
                  )}
                </td>
                <td className="hidden py-1 pr-2 text-right sm:table-cell">
                  {r.board ? <RangeCell p10={r.board.ptsP10} p90={r.board.ptsP90} /> : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
