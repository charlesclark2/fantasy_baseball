"use client"

import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { Nav } from "@/components/nav"
import { AuthGuard } from "@/components/auth-guard"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/lib/auth-context"
import { apiFetch } from "@/lib/api"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TeamSummary = {
  team_id: number
  team_name: string
  team_abbrev: string
  league: string
  division: string
  record: {
    wins: number
    losses: number
    win_pct: number
    run_differential: number | null
    games_back: number | null
    is_division_leader: boolean
    streak_direction: string | null
    streak_length: number | null
  } | null
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ESPN_ABBREV_OVERRIDES: Record<string, string> = {
  CWS: "chw",
  AZ: "ari",
  ATH: "oak",
}

function teamLogoSrc(abbrev: string): string {
  const slug = (ESPN_ABBREV_OVERRIDES[abbrev] ?? abbrev).toLowerCase()
  return `https://a.espncdn.com/i/teamlogos/mlb/500/${slug}.png`
}

const DIVISION_ORDER = [
  "AL East",
  "AL Central",
  "AL West",
  "NL East",
  "NL Central",
  "NL West",
]

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function TeamRow({ team }: { team: TeamSummary }) {
  const rec = team.record
  return (
    <Link
      href={`/team/${team.team_id}`}
      className="flex items-center gap-3 rounded-lg border border-[#262626] bg-[#111111] px-4 py-3 transition-colors hover:border-[#363636] hover:bg-[#161616]"
    >
      <img
        src={teamLogoSrc(team.team_abbrev)}
        alt={team.team_abbrev}
        className="h-9 w-9 shrink-0 object-contain"
        onError={(e) => {
          ;(e.target as HTMLImageElement).style.display = "none"
        }}
      />
      <div className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold text-white">
          {team.team_name}
        </span>
        {rec && (
          <span className="text-xs text-gray-500">
            {rec.wins}–{rec.losses}
            {rec.is_division_leader
              ? " · Leader"
              : rec.games_back
              ? ` · ${rec.games_back} GB`
              : ""}
          </span>
        )}
      </div>
      {rec && (
        <div className="shrink-0 text-right">
          <span className="block text-sm font-semibold tabular-nums text-white">
            {(rec.win_pct * 100).toFixed(1)}%
          </span>
          {rec.streak_direction && rec.streak_length && (
            <span
              className={`text-xs font-semibold ${
                rec.streak_direction === "W" ? "text-emerald-400" : "text-red-400"
              }`}
            >
              {rec.streak_direction}{rec.streak_length}
            </span>
          )}
        </div>
      )}
    </Link>
  )
}

function DivisionSection({
  division,
  teams,
}: {
  division: string
  teams: TeamSummary[]
}) {
  const sorted = [...teams].sort((a, b) => {
    if (!a.record || !b.record) return 0
    return b.record.win_pct - a.record.win_pct
  })

  return (
    <div>
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
        {division}
      </h2>
      <div className="space-y-2">
        {sorted.map((t) => (
          <TeamRow key={t.team_id} team={t} />
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function TeamsPageInner() {
  const { accessToken, email } = useAuth()

  const { data: teams, isLoading, isError } = useQuery<TeamSummary[]>({
    queryKey: ["teams-list"],
    queryFn: () => apiFetch("/teams", {}, accessToken!),
    enabled: !!accessToken,
    staleTime: 1000 * 60 * 30,
  })

  // Group by division
  const byDivision: Record<string, TeamSummary[]> = {}
  for (const team of teams ?? []) {
    const key = `${team.league} ${team.division}`
    if (!byDivision[key]) byDivision[key] = []
    byDivision[key].push(team)
  }

  const divisionGroups = DIVISION_ORDER.map((d) => ({
    label: d,
    teams: byDivision[d] ?? [],
  })).filter((g) => g.teams.length > 0)

  return (
    <>
      <Nav authenticated activeLink="teams" userEmail={email} />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <h1 className="mb-6 text-2xl font-bold text-white">Teams</h1>

        {isLoading && (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="space-y-2">
                <Skeleton className="h-5 w-24" />
                <div className="space-y-1.5">
                  {Array.from({ length: 5 }).map((_, j) => (
                    <Skeleton key={j} className="h-14 w-full rounded-lg" />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {isError && (
          <p className="text-sm text-red-400">
            Failed to load team list. Please try again.
          </p>
        )}

        {!isLoading && !isError && divisionGroups.length === 0 && (
          <p className="text-sm text-gray-500">
            Team profiles not yet available. Check back after the daily refresh.
          </p>
        )}

        {divisionGroups.length > 0 && (
          <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {divisionGroups.map(({ label, teams: divTeams }) => (
              <DivisionSection key={label} division={label} teams={divTeams} />
            ))}
          </div>
        )}
      </main>
    </>
  )
}

export default function TeamsPage() {
  return (
    <AuthGuard>
      <TeamsPageInner />
    </AuthGuard>
  )
}
