"use client"

import { useMemo, useState } from "react"
import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { Search } from "lucide-react"
import { Nav } from "@/components/nav"
import { AuthGuard } from "@/components/auth-guard"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/lib/auth-context"
import { apiFetch } from "@/lib/api"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type BatterSummary = {
  player_id: number
  full_name: string | null
  position: string | null
  bats: string | null
  team: string | null
  season_2026: {
    pa: number | null
    avg: number | null
    obp: number | null
    slg: number | null
    hr: number | null
    woba: number | null
    xwoba: number | null
  } | null
}

type PitcherSummary = {
  player_id: number
  full_name: string | null
  position: string | null
  team: string | null
  season_2026: {
    starts: number | null
    ip: number | null
    era: number | null
    k: number | null
    bb: number | null
    xwoba_against: number | null
  } | null
}

type PlayersListResponse = {
  batters: BatterSummary[]
  pitchers: PitcherSummary[]
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(val: number | null | undefined, decimals = 3): string {
  if (val == null) return "—"
  return val.toFixed(decimals)
}

function fmtAvg(val: number | null | undefined): string {
  if (val == null) return "—"
  return val.toFixed(3).replace(/^0/, "")
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function BatterRow({ batter }: { batter: BatterSummary }) {
  const s = batter.season_2026
  return (
    <Link
      href={`/players/${batter.player_id}`}
      className="grid grid-cols-[1fr_auto] items-center gap-3 rounded-lg border border-[#262626] bg-[#111111] px-4 py-3 transition-colors hover:border-[#363636] hover:bg-[#161616] sm:grid-cols-[1fr_repeat(5,_auto)]"
    >
      <div className="min-w-0">
        <span className="block truncate text-sm font-semibold text-white">
          {batter.full_name ?? `Player ${batter.player_id}`}
        </span>
        <span className="text-xs text-gray-500">
          {batter.team ?? "—"}
          {batter.position ? ` · ${batter.position}` : ""}
          {batter.bats ? ` · B: ${batter.bats}` : ""}
        </span>
      </div>
      <div className="hidden text-right sm:block">
        <span className="block text-xs text-gray-500">AVG</span>
        <span className="block text-sm font-semibold tabular-nums text-white">
          {fmtAvg(s?.avg)}
        </span>
      </div>
      <div className="hidden text-right sm:block">
        <span className="block text-xs text-gray-500">HR</span>
        <span className="block text-sm font-semibold tabular-nums text-white">
          {s?.hr ?? "—"}
        </span>
      </div>
      <div className="hidden text-right sm:block">
        <span className="block text-xs text-gray-500">wOBA</span>
        <span className="block text-sm font-semibold tabular-nums text-white">
          {fmtAvg(s?.woba)}
        </span>
      </div>
      <div className="hidden text-right sm:block">
        <span className="block text-xs text-gray-500">xwOBA</span>
        <span className="block text-sm font-semibold tabular-nums text-white">
          {fmtAvg(s?.xwoba)}
        </span>
      </div>
      <div className="text-right">
        <span className="block text-xs text-gray-500">PA</span>
        <span className="block text-sm font-semibold tabular-nums text-white">
          {s?.pa ?? "—"}
        </span>
      </div>
    </Link>
  )
}

function PitcherRow({ pitcher }: { pitcher: PitcherSummary }) {
  const s = pitcher.season_2026
  return (
    <Link
      href={`/players/${pitcher.player_id}`}
      className="grid grid-cols-[1fr_auto] items-center gap-3 rounded-lg border border-[#262626] bg-[#111111] px-4 py-3 transition-colors hover:border-[#363636] hover:bg-[#161616] sm:grid-cols-[1fr_repeat(5,_auto)]"
    >
      <div className="min-w-0">
        <span className="block truncate text-sm font-semibold text-white">
          {pitcher.full_name ?? `Player ${pitcher.player_id}`}
        </span>
        <span className="text-xs text-gray-500">
          {pitcher.team ?? "—"}
          {pitcher.position ? ` · ${pitcher.position}` : " · SP"}
        </span>
      </div>
      <div className="hidden text-right sm:block">
        <span className="block text-xs text-gray-500">ERA</span>
        <span className="block text-sm font-semibold tabular-nums text-white">
          {fmt(s?.era, 2)}
        </span>
      </div>
      <div className="hidden text-right sm:block">
        <span className="block text-xs text-gray-500">IP</span>
        <span className="block text-sm font-semibold tabular-nums text-white">
          {s?.ip ?? "—"}
        </span>
      </div>
      <div className="hidden text-right sm:block">
        <span className="block text-xs text-gray-500">K</span>
        <span className="block text-sm font-semibold tabular-nums text-white">
          {s?.k ?? "—"}
        </span>
      </div>
      <div className="hidden text-right sm:block">
        <span className="block text-xs text-gray-500">xwOBA</span>
        <span className="block text-sm font-semibold tabular-nums text-white">
          {fmtAvg(s?.xwoba_against)}
        </span>
      </div>
      <div className="text-right">
        <span className="block text-xs text-gray-500">GS</span>
        <span className="block text-sm font-semibold tabular-nums text-white">
          {s?.starts ?? "—"}
        </span>
      </div>
    </Link>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

type TabType = "batters" | "pitchers"

function PlayersPageInner() {
  const { accessToken, email } = useAuth()
  const [search, setSearch] = useState("")
  const [teamFilter, setTeamFilter] = useState("ALL")
  const [tab, setTab] = useState<TabType>("batters")

  const { data, isLoading, isError } = useQuery<PlayersListResponse>({
    queryKey: ["players-list"],
    queryFn: () => apiFetch("/players", {}, accessToken!),
    enabled: !!accessToken,
    staleTime: 1000 * 60 * 30,
  })

  const allTeams = useMemo(() => {
    const teams = new Set<string>()
    for (const b of data?.batters ?? []) if (b.team) teams.add(b.team)
    for (const p of data?.pitchers ?? []) if (p.team) teams.add(p.team)
    return ["ALL", ...Array.from(teams).sort()]
  }, [data])

  const filteredBatters = useMemo(() => {
    const q = search.toLowerCase()
    return (data?.batters ?? []).filter(
      (b) =>
        (teamFilter === "ALL" || b.team === teamFilter) &&
        (b.full_name?.toLowerCase().includes(q) ?? true)
    )
  }, [data, search, teamFilter])

  const filteredPitchers = useMemo(() => {
    const q = search.toLowerCase()
    return (data?.pitchers ?? []).filter(
      (p) =>
        (teamFilter === "ALL" || p.team === teamFilter) &&
        (p.full_name?.toLowerCase().includes(q) ?? true)
    )
  }, [data, search, teamFilter])

  const tabClass = (t: TabType) =>
    t === tab
      ? "rounded-md px-4 py-1.5 text-sm font-medium bg-[#1a1a1a] text-white"
      : "rounded-md px-4 py-1.5 text-sm font-medium text-gray-500 hover:text-gray-300 transition-colors"

  return (
    <>
      <Nav authenticated activeLink="players" userEmail={email} />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <h1 className="mb-6 text-2xl font-bold text-white">Players</h1>

        {/* Controls */}
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          {/* Tabs */}
          <div className="flex items-center gap-1 rounded-lg border border-[#262626] bg-[#0f0f0f] p-1">
            <button className={tabClass("batters")} onClick={() => setTab("batters")}>
              Batters{data ? ` (${filteredBatters.length})` : ""}
            </button>
            <button className={tabClass("pitchers")} onClick={() => setTab("pitchers")}>
              Pitchers{data ? ` (${filteredPitchers.length})` : ""}
            </button>
          </div>

          <div className="flex gap-2">
            {/* Search */}
            <div className="relative flex-1 sm:w-56 sm:flex-none">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-500" />
              <input
                type="text"
                placeholder="Search players…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full rounded-md border border-[#262626] bg-[#111111] py-1.5 pl-8 pr-3 text-sm text-white placeholder:text-gray-600 focus:border-[#363636] focus:outline-none"
              />
            </div>
            {/* Team filter */}
            <select
              value={teamFilter}
              onChange={(e) => setTeamFilter(e.target.value)}
              className="rounded-md border border-[#262626] bg-[#111111] px-3 py-1.5 text-sm text-white focus:border-[#363636] focus:outline-none"
            >
              {allTeams.map((t) => (
                <option key={t} value={t}>
                  {t === "ALL" ? "All Teams" : t}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Header row */}
        {!isLoading && !isError && (
          <div className="mb-2 hidden grid-cols-[1fr_repeat(5,_auto)] gap-3 px-4 sm:grid">
            <span className="text-xs font-semibold uppercase tracking-wider text-gray-600">Player</span>
            {tab === "batters" ? (
              <>
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-600">AVG</span>
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-600">HR</span>
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-600">wOBA</span>
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-600">xwOBA</span>
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-600">PA</span>
              </>
            ) : (
              <>
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-600">ERA</span>
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-600">IP</span>
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-600">K</span>
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-600">xwOBA</span>
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-600">GS</span>
              </>
            )}
          </div>
        )}

        {/* Loading */}
        {isLoading && (
          <div className="space-y-2">
            {Array.from({ length: 10 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full rounded-lg" />
            ))}
          </div>
        )}

        {isError && (
          <p className="text-sm text-red-400">Failed to load players. Please try again.</p>
        )}

        {!isLoading && !isError && tab === "batters" && (
          <>
            {filteredBatters.length === 0 ? (
              <p className="text-sm text-gray-500">No batters match your filters.</p>
            ) : (
              <div className="space-y-1.5">
                {filteredBatters.map((b) => (
                  <BatterRow key={b.player_id} batter={b} />
                ))}
              </div>
            )}
          </>
        )}

        {!isLoading && !isError && tab === "pitchers" && (
          <>
            {filteredPitchers.length === 0 ? (
              <p className="text-sm text-gray-500">No pitchers match your filters.</p>
            ) : (
              <div className="space-y-1.5">
                {filteredPitchers.map((p) => (
                  <PitcherRow key={p.player_id} pitcher={p} />
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </>
  )
}

export default function PlayersPage() {
  return (
    <AuthGuard>
      <PlayersPageInner />
    </AuthGuard>
  )
}
