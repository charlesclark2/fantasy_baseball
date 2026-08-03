"use client"

// NF-C6 Phase 1 — My Teams: a cross-league browse surface, one place to see every imported team's
// roster scored under ITS OWN league's format.
//
// Composes what already exists: NF-C0's saved leagues + NF-C0c's roster name resolution, scored by
// the SAME client-side `buildBoard` every other fantasy surface uses (see `useMyTeams`'s docstring
// in fantasy-queries.ts for why the scoring cannot move server-side — the API Lambda bundles neither
// pandas/numpy nor `quant_sports_intel_models`). No new model, no new scoring logic.
//
// ROS = the season projection (pre-kickoff, so "rest of season" is effectively the full season) —
// labelled honestly, never faked into a per-game number (a per-game figure divided out of a season
// total is false precision). Per-game splits, weekly rest-of-season updates and waiver-wire
// suggestions are PHASE 2, gated on the NF-W1 weekly model — stubbed below as "coming in-season,"
// not built or faked here.

import Link from "next/link"
import { useMyTeams } from "@/lib/fantasy-queries"
import type { MyTeamEntry } from "@/lib/fantasy-queries"
import { EmptyBlock, LoadingBlock, PosBadge, RangeCell, SurfaceHeader, num } from "@/components/fantasy/shared"
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
          {league.source_team_name ? `${league.source_team_name} is` : "Your team is"} linked, but
          the platform reported no rostered players for it — the usual reason is your league
          hasn&rsquo;t drafted yet. Re-import after your draft and the roster will show up here.
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
              <th className="py-1 pr-2 text-right font-medium">Proj. pts (ROS)</th>
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
