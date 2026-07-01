"use client"

import { useState } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { useQuery } from "@tanstack/react-query"
import { ChevronLeft, ChevronRight, Flag } from "lucide-react"
import { Nav } from "@/components/nav"
import { AuthGuard } from "@/components/auth-guard"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/lib/auth-context"
import { apiFetch } from "@/lib/api"
import { PitcherKProjection } from "@/components/pitcher-k-projection"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type BatterSeason = {
  games: number | null
  pa: number | null
  hits: number | null
  hr: number | null
  bb: number | null
  k: number | null
  avg: number | null
  obp: number | null
  slg: number | null
  ops: number | null
  iso: number | null
  woba: number | null
  xwoba: number | null
  xba: number | null
  xslg: number | null
  k_pct: number | null
  bb_pct: number | null
  hard_hit_pct: number | null
  barrel_pct: number | null
  whiff_rate: number | null
}

type BatterRolling = {
  games: number | null
  pa: number | null
  woba: number | null
  xwoba: number | null
  k_pct: number | null
  bb_pct: number | null
  hard_hit_pct: number | null
  barrel_pct: number | null
  whiff_rate: number | null
}

type BatterGameLog = {
  game_pk: number
  date: string
  opp: string | null
  pa: number | null
  hits: number | null
  hr: number | null
  bb: number | null
  k: number | null
  pitches: number | null
}

type PitcherSeason = {
  starts: number | null
  ip: number | null
  total_pitches: number | null
  k: number | null
  bb: number | null
  hbp: number | null
  hr: number | null
  hits: number | null
  runs: number | null
  batters_faced: number | null
  era: number | null
  k9: number | null
  bb9: number | null
  xwoba_against: number | null
  avg_velo: number | null
}

type PitcherGameLog = {
  game_pk: number
  date: string
  opp: string | null
  home_away: "home" | "away"
  ip: number | null
  outs: number | null
  k: number | null
  bb: number | null
  hr: number | null
  hits: number | null
  runs: number | null
  pitches: number | null
  xwoba_against: number | null
  velo: number | null
}

type BatterProfile = {
  player_id: number
  player_type: "batter"
  full_name: string | null
  first_name: string | null
  last_name: string | null
  position: string | null
  bats: string | null
  team: string | null
  birth_date: string | null
  age: number | null
  height_inches: number | null
  weight_lbs: number | null
  is_on_il: boolean
  il_since: string | null
  season_2026: BatterSeason
  rolling_30d: BatterRolling
  game_log: BatterGameLog[]
}

type PitcherProfile = {
  player_id: number
  player_type: "pitcher"
  full_name: string | null
  first_name: string | null
  last_name: string | null
  position: string | null
  team: string | null
  birth_date: string | null
  age: number | null
  height_inches: number | null
  weight_lbs: number | null
  is_on_il: boolean
  il_since: string | null
  season_2026: PitcherSeason
  game_log: PitcherGameLog[]
}

type PlayerProfile = BatterProfile | PitcherProfile

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtAvg(val: number | null | undefined): string {
  if (val == null) return "—"
  return val.toFixed(3).replace(/^0/, "")
}

function fmt(val: number | null | undefined, decimals = 2): string {
  if (val == null) return "—"
  return val.toFixed(decimals)
}

function fmtPct(val: number | null | undefined): string {
  if (val == null) return "—"
  return `${(val * 100).toFixed(1)}%`
}

function fmtHeight(inches: number | null | undefined): string {
  if (inches == null) return "—"
  const ft = Math.floor(inches / 12)
  const inch = inches % 12
  return `${ft}'${inch}"`
}

function fmtIp(ip: number | null | undefined, outs: number | null | undefined): string {
  // innings_pitched may use baseball notation (6.2 = 6⅔ IP) or decimal
  // Store both; prefer outs_recorded for display
  if (outs != null) {
    const full = Math.floor(outs / 3)
    const rem = outs % 3
    return rem === 0 ? `${full}.0` : `${full}.${rem}`
  }
  if (ip != null) return ip.toFixed(1)
  return "—"
}

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[#262626] bg-[#111111] px-4 py-3 text-center">
      <span className="block text-xs font-semibold uppercase tracking-wider text-gray-500">
        {label}
      </span>
      <span className="mt-1 block text-xl font-bold tabular-nums text-white">{value}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Batter view
// ---------------------------------------------------------------------------

const LOG_PAGE_SIZE = 30

function BatterView({ profile }: { profile: BatterProfile }) {
  const s = profile.season_2026
  const r = profile.rolling_30d
  const log = [...profile.game_log].reverse() // newest first
  const [logPage, setLogPage] = useState(0)
  const logStart = logPage * LOG_PAGE_SIZE
  const logEnd = Math.min(logStart + LOG_PAGE_SIZE, log.length)
  const visibleLog = log.slice(logStart, logEnd)

  return (
    <>
      {/* Season stats */}
      <section className="mb-8">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
          2026 Season
        </h2>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-9">
          <StatCard label="PA" value={s.pa?.toString() ?? "—"} />
          <StatCard label="AVG" value={fmtAvg(s.avg)} />
          <StatCard label="OBP" value={fmtAvg(s.obp)} />
          <StatCard label="SLG" value={fmtAvg(s.slg)} />
          <StatCard label="OPS" value={fmtAvg(s.ops)} />
          <StatCard label="HR" value={s.hr?.toString() ?? "—"} />
          <StatCard label="BB" value={s.bb?.toString() ?? "—"} />
          <StatCard label="wOBA" value={fmtAvg(s.woba)} />
          <StatCard label="xwOBA" value={fmtAvg(s.xwoba)} />
        </div>
      </section>

      {/* Batted ball / discipline */}
      <section className="mb-8">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
          Batted Ball &amp; Discipline
        </h2>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-5">
          <StatCard label="K%" value={fmtPct(s.k_pct)} />
          <StatCard label="BB%" value={fmtPct(s.bb_pct)} />
          <StatCard label="Hard Hit%" value={fmtPct(s.hard_hit_pct)} />
          <StatCard label="Barrel%" value={fmtPct(s.barrel_pct)} />
          <StatCard label="Whiff%" value={fmtPct(s.whiff_rate)} />
        </div>
      </section>

      {/* Last 30 days */}
      <section className="mb-8">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
          Last 30 Days
          {r.games != null ? ` (${r.games} G, ${r.pa ?? "—"} PA)` : ""}
        </h2>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-5">
          <StatCard label="wOBA" value={fmtAvg(r.woba)} />
          <StatCard label="xwOBA" value={fmtAvg(r.xwoba)} />
          <StatCard label="K%" value={fmtPct(r.k_pct)} />
          <StatCard label="Hard Hit%" value={fmtPct(r.hard_hit_pct)} />
          <StatCard label="Barrel%" value={fmtPct(r.barrel_pct)} />
        </div>
      </section>

      {/* Game log */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
            Game Log ({log.length} games)
          </h2>
          {log.length > LOG_PAGE_SIZE && (
            <span className="text-xs text-gray-600">
              {logStart + 1}–{logEnd} of {log.length}
            </span>
          )}
        </div>
        <div className="overflow-x-auto rounded-lg border border-[#262626]">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#262626] text-xs font-semibold uppercase tracking-wider text-gray-500">
                <th className="px-3 py-2.5 text-left">Date</th>
                <th className="px-3 py-2.5 text-left">Opp</th>
                <th className="px-3 py-2.5 text-right">PA</th>
                <th className="px-3 py-2.5 text-right">H</th>
                <th className="px-3 py-2.5 text-right">HR</th>
                <th className="px-3 py-2.5 text-right">BB</th>
                <th className="px-3 py-2.5 text-right">K</th>
                <th className="hidden px-3 py-2.5 text-right sm:table-cell">P</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1a1a1a]">
              {visibleLog.map((g) => (
                <tr
                  key={g.game_pk}
                  className="text-white transition-colors hover:bg-[#161616]"
                >
                  <td className="whitespace-nowrap px-3 py-2 text-gray-400">{g.date}</td>
                  <td className="px-3 py-2 font-medium">{g.opp ?? "—"}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{g.pa ?? "—"}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{g.hits ?? "—"}</td>
                  <td className={`px-3 py-2 text-right tabular-nums font-semibold ${(g.hr ?? 0) > 0 ? "text-emerald-400" : ""}`}>
                    {g.hr ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{g.bb ?? "—"}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{g.k ?? "—"}</td>
                  <td className="hidden px-3 py-2 text-right tabular-nums text-gray-500 sm:table-cell">
                    {g.pitches ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {log.length > LOG_PAGE_SIZE && (
          <div className="mt-3 flex items-center justify-center gap-2">
            <button
              onClick={() => setLogPage((p) => Math.max(0, p - 1))}
              disabled={logPage === 0}
              className="flex items-center gap-1 rounded-md border border-[#262626] bg-[#111111] px-3 py-1.5 text-xs text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              Prev
            </button>
            <button
              onClick={() => setLogPage((p) => (p + 1) * LOG_PAGE_SIZE < log.length ? p + 1 : p)}
              disabled={logEnd >= log.length}
              className="flex items-center gap-1 rounded-md border border-[#262626] bg-[#111111] px-3 py-1.5 text-xs text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              Next
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </section>
    </>
  )
}

// ---------------------------------------------------------------------------
// Pitcher view
// ---------------------------------------------------------------------------

function PitcherView({ profile }: { profile: PitcherProfile }) {
  const s = profile.season_2026
  const log = [...profile.game_log].reverse()
  const [logPage, setLogPage] = useState(0)
  const logStart = logPage * LOG_PAGE_SIZE
  const logEnd = Math.min(logStart + LOG_PAGE_SIZE, log.length)
  const visibleLog = log.slice(logStart, logEnd)

  return (
    <>
      {/* Season stats */}
      <section className="mb-8">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
          2026 Season
        </h2>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-8">
          <StatCard label="GS" value={s.starts?.toString() ?? "—"} />
          <StatCard label="IP" value={s.ip?.toString() ?? "—"} />
          <StatCard label="ERA" value={fmt(s.era, 2)} />
          <StatCard label="K" value={s.k?.toString() ?? "—"} />
          <StatCard label="BB" value={s.bb?.toString() ?? "—"} />
          <StatCard label="K/9" value={fmt(s.k9, 1)} />
          <StatCard label="BB/9" value={fmt(s.bb9, 1)} />
          <StatCard label="xwOBA" value={fmtAvg(s.xwoba_against)} />
        </div>
      </section>

      {/* Velocity */}
      {s.avg_velo != null && (
        <section className="mb-8">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
            Most Recent Start
          </h2>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-4">
            <StatCard label="Avg Velo" value={`${fmt(s.avg_velo, 1)} mph`} />
            <StatCard label="HR Allowed" value={s.hr?.toString() ?? "—"} />
            <StatCard label="HBP" value={s.hbp?.toString() ?? "—"} />
            <StatCard label="BF" value={s.batters_faced?.toString() ?? "—"} />
          </div>
        </section>
      )}

      {/* Strikeout projection (E5.5) — renders only when a projection is served for this pitcher */}
      <PitcherKProjection pitcherId={profile.player_id} />

      {/* Game log */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
            Game Log ({log.length} starts)
          </h2>
          {log.length > LOG_PAGE_SIZE && (
            <span className="text-xs text-gray-600">
              {logStart + 1}–{logEnd} of {log.length}
            </span>
          )}
        </div>
        <div className="overflow-x-auto rounded-lg border border-[#262626]">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#262626] text-xs font-semibold uppercase tracking-wider text-gray-500">
                <th className="px-3 py-2.5 text-left">Date</th>
                <th className="px-3 py-2.5 text-left">Opp</th>
                <th className="px-3 py-2.5 text-right">IP</th>
                <th className="px-3 py-2.5 text-right">K</th>
                <th className="px-3 py-2.5 text-right">BB</th>
                <th className="px-3 py-2.5 text-right">H</th>
                <th className="px-3 py-2.5 text-right">R</th>
                <th className="px-3 py-2.5 text-right">HR</th>
                <th className="hidden px-3 py-2.5 text-right sm:table-cell">P</th>
                <th className="hidden px-3 py-2.5 text-right sm:table-cell">xwOBA</th>
                <th className="hidden px-3 py-2.5 text-right lg:table-cell">Velo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1a1a1a]">
              {visibleLog.map((g) => (
                <tr
                  key={g.game_pk}
                  className="text-white transition-colors hover:bg-[#161616]"
                >
                  <td className="whitespace-nowrap px-3 py-2 text-gray-400">{g.date}</td>
                  <td className="px-3 py-2 font-medium">
                    {g.opp ?? "—"}
                    <span className="ml-1 text-xs text-gray-600">
                      {g.home_away === "home" ? "vs" : "@"}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {fmtIp(g.ip, g.outs)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums font-semibold">
                    {g.k ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{g.bb ?? "—"}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{g.hits ?? "—"}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{g.runs ?? "—"}</td>
                  <td className={`px-3 py-2 text-right tabular-nums ${(g.hr ?? 0) > 0 ? "text-red-400" : ""}`}>
                    {g.hr ?? "—"}
                  </td>
                  <td className="hidden px-3 py-2 text-right tabular-nums text-gray-500 sm:table-cell">
                    {g.pitches ?? "—"}
                  </td>
                  <td className="hidden px-3 py-2 text-right tabular-nums sm:table-cell">
                    {g.xwoba_against != null ? fmtAvg(g.xwoba_against) : "—"}
                  </td>
                  <td className="hidden px-3 py-2 text-right tabular-nums text-gray-400 lg:table-cell">
                    {g.velo != null ? `${fmt(g.velo, 1)}` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {log.length > LOG_PAGE_SIZE && (
          <div className="mt-3 flex items-center justify-center gap-2">
            <button
              onClick={() => setLogPage((p) => Math.max(0, p - 1))}
              disabled={logPage === 0}
              className="flex items-center gap-1 rounded-md border border-[#262626] bg-[#111111] px-3 py-1.5 text-xs text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              Prev
            </button>
            <button
              onClick={() => setLogPage((p) => (p + 1) * LOG_PAGE_SIZE < log.length ? p + 1 : p)}
              disabled={logEnd >= log.length}
              className="flex items-center gap-1 rounded-md border border-[#262626] bg-[#111111] px-3 py-1.5 text-xs text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              Next
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </section>
    </>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function PlayerPageInner() {
  const { player_id } = useParams<{ player_id: string }>()
  const { accessToken, email } = useAuth()

  const { data: profile, isLoading, isError } = useQuery<PlayerProfile>({
    queryKey: ["player", player_id],
    queryFn: () => apiFetch(`/players/${player_id}`, {}, accessToken!),
    enabled: !!accessToken,
    staleTime: 1000 * 60 * 30,
  })

  const displayName = profile?.full_name ?? `Player ${player_id}`

  return (
    <>
      <Nav authenticated activeLink="players" userEmail={email} />
      <main className="mx-auto max-w-6xl px-4 py-8">
        {/* Back link */}
        <Link
          href="/players"
          className="mb-5 inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          Players
        </Link>

        {isLoading && (
          <div className="space-y-4">
            <Skeleton className="h-10 w-48" />
            <div className="grid grid-cols-5 gap-2">
              {Array.from({ length: 9 }).map((_, i) => (
                <Skeleton key={i} className="h-20 rounded-lg" />
              ))}
            </div>
            <Skeleton className="h-64 rounded-lg" />
          </div>
        )}

        {isError && (
          <p className="text-sm text-red-400">Player not found or profile unavailable.</p>
        )}

        {profile && (
          <>
            {/* Header */}
            <div className="mb-6 flex items-center gap-5">
              {/* Headshot */}
              <div className="h-20 w-20 flex-shrink-0 overflow-hidden rounded-full border-2 border-[#262626] bg-[#1a1a1a]">
                <img
                  src={`https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png/w_180,q_auto:best/v1/people/${profile.player_id}/headshot/67/current`}
                  alt={displayName}
                  className="h-full w-full object-cover"
                />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <h1 className="text-3xl font-bold text-white">{displayName}</h1>
                    {profile.is_on_il && (
                      <span
                        className="flex-shrink-0 rounded bg-red-900/60 px-2 py-0.5 text-xs font-bold uppercase tracking-wide text-red-400 border border-red-800/60"
                        title={profile.il_since ? `On IL since ${profile.il_since}` : "On injured list"}
                      >
                        IL
                      </span>
                    )}
                  </div>
                  <a
                    href={`mailto:support@credencesports.com?subject=${encodeURIComponent(`Data Quality Issue: Player ${profile.player_id} (${displayName})`)}&body=${encodeURIComponent(`Player ID: ${profile.player_id}\nPlayer Name: ${displayName}\n\nDescribe the issue:\n`)}`}
                    className="flex-shrink-0 flex items-center gap-1.5 rounded-md border border-[#262626] bg-[#111111] px-2.5 py-1.5 text-xs text-gray-500 hover:text-gray-300 hover:border-[#363636] transition-colors"
                    title="Report a data quality issue"
                  >
                    <Flag className="h-3 w-3" />
                    Report issue
                  </a>
                </div>
                <p className="mt-1 text-sm text-gray-500">
                  {profile.team ?? "—"}
                  {profile.position ? ` · ${profile.position}` : ""}
                  {profile.player_type === "batter" && (profile as BatterProfile).bats
                    ? ` · Bats: ${(profile as BatterProfile).bats}`
                    : ""}
                  {profile.age != null ? ` · Age ${profile.age}` : ""}
                  {profile.height_inches != null ? ` · ${fmtHeight(profile.height_inches)}` : ""}
                  {profile.weight_lbs != null ? `, ${profile.weight_lbs} lbs` : ""}
                  <span className="ml-2 rounded bg-[#1a1a1a] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                    {profile.player_type === "batter" ? "Batter" : "Pitcher"}
                  </span>
                </p>
              </div>
            </div>

            {profile.player_type === "batter" ? (
              <BatterView profile={profile as BatterProfile} />
            ) : (
              <PitcherView profile={profile as PitcherProfile} />
            )}
          </>
        )}
      </main>
    </>
  )
}

export default function PlayerPage() {
  return (
    <AuthGuard>
      <PlayerPageInner />
    </AuthGuard>
  )
}
