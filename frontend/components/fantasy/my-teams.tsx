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
import { EXPECTED_POINTS_LABEL } from "@/lib/fantasy-claim-copy"
import type { RosterMatch } from "@/lib/league-scoring"

export function MyTeams() {
  const { teams, isLoading, isError } = useMyTeams()

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <SurfaceHeader
        title="My Teams"
        blurb="Every league you've imported, in one place — each roster scored under that league's own format. Projections are the rest-of-season figure (pre-kickoff, so this is effectively the full season)."
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
          {teams.map((entry) => (
            <LeagueCard key={entry.league.league_id} entry={entry} />
          ))}
        </div>
      )}
    </div>
  )
}

function LeagueCard({ entry }: { entry: MyTeamEntry }) {
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
          <RosterTable label="Starters" rows={starters} />
          <RosterTable label="Bench" rows={bench} />
          {unmatchedCount > 0 && (
            <p className="mt-2 text-[11px] text-gray-600">
              {matchedCount} of {roster.length} rostered players matched to a season projection; the
              rest are shown without one (a name we could not resolve, or a player we do not
              project).
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

function RosterTable({ label, rows }: { label: string; rows: RosterMatch[] }) {
  if (rows.length === 0) return null
  return (
    <div className="mt-4">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
        {label} · {rows.length}
      </div>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[480px] text-left text-[11px]">
          <thead>
            <tr className="text-gray-600">
              <th className="py-1 pr-2 font-medium">Player</th>
              <th className="py-1 pr-2 font-medium">Pos</th>
              <th className="py-1 pr-2 font-medium">Team</th>
              <th className="py-1 pr-2 text-right font-medium">
                <InfoTip label={`${EXPECTED_POINTS_LABEL} (ROS)`}>{GLOSSARY.expectedPoints}</InfoTip>
              </th>
              <th className="py-1 pr-2 text-right font-medium">80% range</th>
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
                <td className="py-1 pr-2 text-gray-500">{r.roster.team ?? "—"}</td>
                <td className="py-1 pr-2 text-right text-gray-200">
                  {r.board ? num(r.board.pts) : <span className="text-gray-600">not matched</span>}
                </td>
                <td className="py-1 pr-2 text-right">
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
