"use client"

import { useParams } from "next/navigation"
import { useQuery } from "@tanstack/react-query"
import { format, parseISO } from "date-fns"
import { TrendingUp, TrendingDown, Minus } from "lucide-react"
import { Nav } from "@/components/nav"
import { AuthGuard } from "@/components/auth-guard"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/lib/auth-context"
import { apiFetch } from "@/lib/api"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type PlatoonSplit = {
  xwoba: number | null
  woba: number | null
  k_pct: number | null
  bb_pct: number | null
  runs_per_game: number | null
}

type FormGame = {
  game_pk: number
  date: string
  opponent: string
  home_away: "home" | "away"
  runs_scored: number
  runs_allowed: number
  won: boolean
}

type ScheduleGame = {
  game_pk: number
  date: string
  opponent: string
  home_away: "home" | "away"
  venue_name: string | null
  our_probable_pitcher: string | null
}

type TeamProfile = {
  team_id: number
  team_abbrev: string
  team_name: string
  league: string
  division: string
  record: {
    wins: number
    losses: number
    games_played: number
    win_pct: number
    runs_scored_ytd: number
    runs_allowed_ytd: number
    run_differential: number | null
    pythagorean_win_exp: number | null
    games_back: number
    is_division_leader: boolean
    streak_direction: string | null
    streak_length: number | null
  }
  offense: {
    xwoba_std: number | null
    woba_std: number | null
    runs_per_game_std: number | null
    k_pct_std: number | null
    bb_pct_std: number | null
    xwoba_30d: number | null
    runs_per_game_30d: number | null
    vs_lhp: PlatoonSplit | null
    vs_rhp: PlatoonSplit | null
  }
  pitching: {
    ra9: number | null
    xwoba_against_std: number | null
    starter_xwoba_against_std: number | null
    starter_k_pct_std: number | null
    bullpen_xwoba_against_std: number | null
    xwoba_against_30d: number | null
  }
  elo: {
    current: number | null
    history: { date: string; elo: number }[]
  }
  recent_form: FormGame[]
  schedule: ScheduleGame[]
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pct(val: number | null | undefined, decimals = 1): string {
  if (val == null) return "—"
  return `${(val * 100).toFixed(decimals)}%`
}

function num(val: number | null | undefined, decimals = 3): string {
  if (val == null) return "—"
  return val.toFixed(decimals)
}

function rdSign(val: number | null): string {
  if (val == null) return "—"
  return val > 0 ? `+${val}` : `${val}`
}

function fmtDate(dateStr: string): string {
  try {
    return format(parseISO(dateStr), "MMM d")
  } catch {
    return dateStr
  }
}

function fmtDow(dateStr: string): string {
  try {
    return format(parseISO(dateStr), "EEE")
  } catch {
    return ""
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatCard({
  label,
  value,
  sub,
}: {
  label: string
  value: string
  sub?: string
}) {
  return (
    <div className="flex flex-col gap-0.5 rounded-lg border border-[#262626] bg-[#111111] px-4 py-3">
      <span className="text-xs text-gray-500">{label}</span>
      <span className="text-xl font-semibold text-white tabular-nums">{value}</span>
      {sub && <span className="text-xs text-gray-500">{sub}</span>}
    </div>
  )
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-400">
      {children}
    </h2>
  )
}

function PlatoonRow({
  hand,
  split,
}: {
  hand: string
  split: PlatoonSplit | null
}) {
  if (!split) return null
  return (
    <div className="flex items-center gap-6 rounded-lg border border-[#262626] bg-[#111111] px-4 py-3">
      <span className="w-16 text-sm font-medium text-gray-400">vs {hand}</span>
      <div className="flex flex-1 gap-6">
        <div className="flex flex-col">
          <span className="text-xs text-gray-500">xwOBA</span>
          <span className="text-sm font-semibold text-white tabular-nums">
            {num(split.xwoba)}
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-xs text-gray-500">wOBA</span>
          <span className="text-sm font-semibold text-white tabular-nums">
            {num(split.woba)}
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-xs text-gray-500">K%</span>
          <span className="text-sm font-semibold text-white tabular-nums">
            {pct(split.k_pct)}
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-xs text-gray-500">BB%</span>
          <span className="text-sm font-semibold text-white tabular-nums">
            {pct(split.bb_pct)}
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-xs text-gray-500">R/G</span>
          <span className="text-sm font-semibold text-white tabular-nums">
            {num(split.runs_per_game, 2)}
          </span>
        </div>
      </div>
    </div>
  )
}

function EloSparkline({ history }: { history: { date: string; elo: number }[] }) {
  if (!history.length) return <span className="text-xs text-gray-600">No data</span>

  const elos = history.map((h) => h.elo)
  const min = Math.min(...elos)
  const max = Math.max(...elos)
  const range = max - min || 1
  const W = 200
  const H = 40

  const points = history.map((h, i) => {
    const x = (i / (history.length - 1 || 1)) * W
    const y = H - ((h.elo - min) / range) * H
    return `${x},${y}`
  })

  const trend = elos[elos.length - 1] - elos[0]
  const color = trend > 5 ? "#10b981" : trend < -5 ? "#ef4444" : "#6b7280"

  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function TeamPageInner() {
  const params = useParams<{ team_id: string }>()
  const { accessToken, email } = useAuth()

  const { data: team, isLoading, isError } = useQuery<TeamProfile>({
    queryKey: ["team", params.team_id],
    queryFn: () => apiFetch(`/teams/${params.team_id}`, {}, accessToken),
    enabled: !!accessToken && !!params.team_id,
    staleTime: 5 * 60 * 1000,
  })

  return (
    <>
      <Nav authenticated activeLink={null} userEmail={email} />
      <main className="mx-auto max-w-5xl px-4 py-8">
        {isLoading && (
          <div className="space-y-4">
            <Skeleton className="h-12 w-64 bg-[#1a1a1a]" />
            <div className="grid grid-cols-4 gap-3">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-20 bg-[#1a1a1a]" />
              ))}
            </div>
          </div>
        )}

        {isError && (
          <div className="rounded-lg border border-[#262626] bg-[#111111] p-8 text-center text-gray-400">
            Team profile not found or not yet available.
          </div>
        )}

        {team && (
          <div className="space-y-8">
            {/* Header */}
            <div className="flex items-start justify-between">
              <div>
                <h1 className="text-3xl font-bold text-white">{team.team_name}</h1>
                <p className="mt-1 text-sm text-gray-400">
                  {team.division} · {team.league}
                </p>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-white tabular-nums">
                  {team.record.wins}–{team.record.losses}
                </div>
                <div className="mt-0.5 flex items-center justify-end gap-2">
                  {team.record.streak_direction && team.record.streak_length && (
                    <span
                      className={`rounded px-1.5 py-0.5 text-xs font-semibold ${
                        team.record.streak_direction === "W"
                          ? "bg-emerald-900/50 text-emerald-400"
                          : "bg-red-900/50 text-red-400"
                      }`}
                    >
                      {team.record.streak_direction}{team.record.streak_length}
                    </span>
                  )}
                  {team.record.is_division_leader ? (
                    <span className="text-xs text-emerald-400">Division Leader</span>
                  ) : (
                    <span className="text-xs text-gray-500">
                      {team.record.games_back != null && team.record.games_back > 0
                        ? `${team.record.games_back} GB`
                        : ""}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Key stats grid */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatCard
                label="Run Diff"
                value={rdSign(team.record.run_differential)}
                sub={`${team.record.runs_scored_ytd} RS · ${team.record.runs_allowed_ytd} RA`}
              />
              <StatCard
                label="xWin%"
                value={pct(team.record.pythagorean_win_exp)}
                sub="Pythagorean"
              />
              <StatCard
                label="Off xwOBA"
                value={num(team.offense.xwoba_std)}
                sub={`30D: ${num(team.offense.xwoba_30d)}`}
              />
              <StatCard
                label="R/G"
                value={num(team.offense.runs_per_game_std, 2)}
                sub={`30D: ${num(team.offense.runs_per_game_30d, 2)}`}
              />
              <StatCard
                label="RA/9"
                value={num(team.pitching.ra9, 2)}
                sub="Runs allowed per game"
              />
              <StatCard
                label="Pit xwOBA-against"
                value={num(team.pitching.xwoba_against_std)}
                sub={`30D: ${num(team.pitching.xwoba_against_30d)}`}
              />
              <StatCard
                label="SP K%"
                value={pct(team.pitching.starter_k_pct_std)}
                sub="Starter strikeout rate"
              />
              <StatCard
                label="BP xwOBA"
                value={num(team.pitching.bullpen_xwoba_against_std)}
                sub="Bullpen xwOBA-against"
              />
            </div>

            {/* ELO + Platoon splits */}
            <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
              {/* ELO */}
              <div>
                <SectionHeader>ELO Rating</SectionHeader>
                <div className="rounded-lg border border-[#262626] bg-[#111111] px-4 py-4">
                  <div className="mb-3 flex items-end justify-between">
                    <span className="text-2xl font-bold text-white tabular-nums">
                      {team.elo.current != null ? Math.round(team.elo.current) : "—"}
                    </span>
                    {team.elo.history.length >= 2 && (() => {
                      const diff =
                        team.elo.history[team.elo.history.length - 1].elo -
                        team.elo.history[0].elo
                      return (
                        <span
                          className={`flex items-center gap-1 text-sm ${
                            diff > 5
                              ? "text-emerald-400"
                              : diff < -5
                              ? "text-red-400"
                              : "text-gray-500"
                          }`}
                        >
                          {diff > 5 ? (
                            <TrendingUp className="h-3.5 w-3.5" />
                          ) : diff < -5 ? (
                            <TrendingDown className="h-3.5 w-3.5" />
                          ) : (
                            <Minus className="h-3.5 w-3.5" />
                          )}
                          {diff > 0 ? "+" : ""}
                          {diff.toFixed(0)} (30 days)
                        </span>
                      )
                    })()}
                  </div>
                  <EloSparkline history={team.elo.history} />
                </div>
              </div>

              {/* Platoon splits */}
              <div>
                <SectionHeader>vs Pitcher Hand (Season)</SectionHeader>
                <div className="space-y-2">
                  <PlatoonRow hand="LHP" split={team.offense.vs_lhp ?? null} />
                  <PlatoonRow hand="RHP" split={team.offense.vs_rhp ?? null} />
                </div>
              </div>
            </div>

            {/* Recent form */}
            {team.recent_form.length > 0 && (
              <div>
                <SectionHeader>Recent Form (L10)</SectionHeader>
                <div className="flex gap-1.5 flex-wrap">
                  {team.recent_form.map((g) => (
                    <div
                      key={g.game_pk}
                      title={`${fmtDate(g.date)} vs ${g.opponent} (${g.home_away}) ${g.runs_scored}–${g.runs_allowed}`}
                      className={`flex h-8 w-8 items-center justify-center rounded text-xs font-bold ${
                        g.won
                          ? "bg-emerald-900/60 text-emerald-400"
                          : "bg-red-900/60 text-red-400"
                      }`}
                    >
                      {g.won ? "W" : "L"}
                    </div>
                  ))}
                </div>
                {/* Detailed form table */}
                <div className="mt-3 overflow-x-auto rounded-lg border border-[#262626]">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-[#262626] text-left text-gray-500">
                        <th className="px-3 py-2 font-medium">Date</th>
                        <th className="px-3 py-2 font-medium">Opponent</th>
                        <th className="px-3 py-2 font-medium"></th>
                        <th className="px-3 py-2 font-medium text-right">Score</th>
                        <th className="px-3 py-2 font-medium text-right">Result</th>
                      </tr>
                    </thead>
                    <tbody>
                      {team.recent_form.map((g, i) => (
                        <tr
                          key={g.game_pk}
                          className={`border-b border-[#1a1a1a] ${i % 2 === 0 ? "bg-[#0d0d0d]" : ""}`}
                        >
                          <td className="px-3 py-2 text-gray-400">{fmtDate(g.date)}</td>
                          <td className="px-3 py-2 font-medium text-white">{g.opponent}</td>
                          <td className="px-3 py-2 text-gray-500">{g.home_away === "home" ? "vs" : "@"}</td>
                          <td className="px-3 py-2 text-right tabular-nums text-gray-300">
                            {g.runs_scored}–{g.runs_allowed}
                          </td>
                          <td
                            className={`px-3 py-2 text-right font-semibold ${
                              g.won ? "text-emerald-400" : "text-red-400"
                            }`}
                          >
                            {g.won ? "W" : "L"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Upcoming schedule */}
            {team.schedule.length > 0 && (
              <div>
                <SectionHeader>Upcoming Schedule</SectionHeader>
                <div className="overflow-x-auto rounded-lg border border-[#262626]">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-[#262626] text-left text-gray-500">
                        <th className="px-3 py-2 font-medium">Day</th>
                        <th className="px-3 py-2 font-medium">Date</th>
                        <th className="px-3 py-2 font-medium">Opponent</th>
                        <th className="px-3 py-2 font-medium"></th>
                        <th className="px-3 py-2 font-medium">Our Starter</th>
                      </tr>
                    </thead>
                    <tbody>
                      {team.schedule.map((g, i) => (
                        <tr
                          key={g.game_pk}
                          className={`border-b border-[#1a1a1a] ${i % 2 === 0 ? "bg-[#0d0d0d]" : ""}`}
                        >
                          <td className="px-3 py-2 text-gray-500">{fmtDow(g.date)}</td>
                          <td className="px-3 py-2 text-gray-400">{fmtDate(g.date)}</td>
                          <td className="px-3 py-2 font-medium text-white">{g.opponent}</td>
                          <td className="px-3 py-2 text-gray-500">{g.home_away === "home" ? "vs" : "@"}</td>
                          <td className="px-3 py-2 text-gray-300">
                            {g.our_probable_pitcher ?? <span className="text-gray-600">TBD</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </>
  )
}

export default function TeamPage() {
  return (
    <AuthGuard>
      <TeamPageInner />
    </AuthGuard>
  )
}
