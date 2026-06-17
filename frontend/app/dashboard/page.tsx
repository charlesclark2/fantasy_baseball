"use client"

import React, { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import posthog from "posthog-js"
import { useQuery } from "@tanstack/react-query"
import { format } from "date-fns"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ProbabilityBar } from "@/components/probability-bar"
import { PipelineStatusDot } from "@/components/pipeline-status-dot"
import { Nav } from "@/components/nav"
import { AuthGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { apiFetch } from "@/lib/api"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { CalendarIcon, TrendingUp } from "lucide-react"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"
import { useSelectedDate } from "@/lib/date-context"
import { normalizeTeam } from "@/lib/teams"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Pick = {
  game_pk: number
  game_date: string
  market_type: string
  model_prob: number
  bovada_devig_prob: number
  edge: number
  game_conviction_score: number
  win_prob_ci_low: number | null
  win_prob_ci_high: number | null
  win_prob_ci_width: number | null
  gate_signals_met: number | null
  lineup_confirmed: boolean
  home_team: string
  away_team: string
  pick_side: string | null
  game_start_utc: string | null
  model_total_runs: number | null
  market_total_line: number | null
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(val: number) {
  return `${(val * 100).toFixed(1)}%`
}

/** Returns true if the pick side flips the raw home/over probability. */
function isSideFlipped(pick: Pick): boolean {
  return pick.pick_side === "away" || pick.pick_side === "under"
}

/**
 * Display probability as distance above 50/50 from the pick side's perspective.
 * e.g. away pick with model_prob=0.314 (home) → away_prob=0.686 → display "+18.6%"
 */
function fmtPickSideProb(pick: Pick, rawProb: number | null): string {
  if (rawProb == null) return "—"
  const sideProb = isSideFlipped(pick) ? 1 - rawProb : rawProb
  const delta = (sideProb - 0.5) * 100
  return `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}%`
}

/** Edge from the pick side's perspective — always positive for a favorable bet. */
function fmtPickSideEdge(pick: Pick): string {
  if (pick.edge == null) return "—"
  // h2h edge is in home-win space; totals edge is in over space. Negate for flipped sides.
  const val = isSideFlipped(pick) ? -pick.edge : pick.edge
  return `${val >= 0 ? "+" : ""}${pick.market_type === "totals" ? val.toFixed(2) : (val * 100).toFixed(1) + "%"}`
}

function fmtGameTime(utc: string | null): string | null {
  if (!utc) return null
  const iso = utc.endsWith("Z") || /[+-]\d\d:?\d\d$/.test(utc) ? utc : utc + "Z"
  const d = new Date(iso)
  if (isNaN(d.getTime())) return null
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", timeZoneName: "short" })
}

function conviction(score: number): string {
  if (score > 0.70) return "HIGH"
  if (score > 0.50) return "MED"
  return "LOW"
}

function pickSideLabel(pick: Pick): string {
  if (pick.market_type === "totals") {
    return pick.pick_side === "over" ? "Over" : "Under"
  }
  if (pick.pick_side === "home") return pick.home_team ?? "Home"
  if (pick.pick_side === "away") return pick.away_team ?? "Away"
  return ""
}


function normalizeEVPick(p: any): Pick {
  const edge = p.edge ?? 0
  const isTotal = p.market_type === "totals"
  const pick_side = isTotal ? (edge >= 0 ? "over" : "under") : (edge >= 0 ? "home" : "away")
  return {
    game_pk: p.game_pk,
    game_date: p.game_date ?? "",
    market_type: p.market_type ?? "h2h",
    model_prob: p.model_prob ?? 0,
    bovada_devig_prob: p.bovada_devig_prob ?? 0,
    edge,
    game_conviction_score: p.game_conviction_score ?? 0,
    win_prob_ci_low: null,
    win_prob_ci_high: null,
    win_prob_ci_width: null,
    gate_signals_met: null,
    lineup_confirmed: p.lineup_confirmed ?? false,
    home_team: normalizeTeam(p.home_team ?? ""),
    away_team: normalizeTeam(p.away_team ?? ""),
    pick_side,
    game_start_utc: p.game_start_utc ?? null,
    model_total_runs: p.pred_total_runs ?? null,
    market_total_line: p.total_line_consensus ?? null,
  }
}

const CONVICTION_TOOLTIP: Record<string, string> = {
  HIGH: "Model conviction (early) — strong confidence in this edge based on the signal active today. Note: only 1 of 5 gate criteria is live; this score reflects model certainty, not a full multi-signal gate.",
  MED: "Model conviction (early) — moderate confidence. Most model signals align but with some uncertainty. Note: only 1 of 5 gate criteria is active.",
  LOW: "Model conviction (early) — lower confidence. Edge detected but model uncertainty is higher. Note: only 1 of 5 gate criteria is active.",
}

function ConvictionBadge({ level }: { level: string }) {
  const badge =
    level === "HIGH" ? (
      <Badge className="bg-[#10b981] text-[#0a0a0a] text-xs font-bold uppercase tracking-widest cursor-default">
        HIGH
      </Badge>
    ) : level === "MED" ? (
      <Badge
        variant="outline"
        className="border-[#f59e0b] text-[#f59e0b] text-xs font-bold uppercase tracking-widest cursor-default"
      >
        MED
      </Badge>
    ) : (
      <Badge
        variant="outline"
        className="border-gray-600 text-gray-500 text-xs font-bold uppercase tracking-widest cursor-default"
      >
        LOW
      </Badge>
    )

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>{badge}</TooltipTrigger>
        <TooltipContent side="top" className="max-w-[200px] text-xs text-center text-white bg-[#1a1a1a] border-[#262626]">
          {CONVICTION_TOOLTIP[level] ?? ""}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------


function PageHeader({ picks, isLoading, rightSlot }: { picks: Pick[]; isLoading: boolean; rightSlot: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-6xl px-4 pt-4 pb-3 flex items-center justify-between">
      <PipelineStatusDot picks={picks} isLoading={isLoading} />
      {rightSlot}
    </div>
  )
}

const TH = "text-xs uppercase tracking-wider text-gray-500 font-medium"

function PickRow({ pick, router }: { pick: Pick; router: ReturnType<typeof useRouter> }) {
  const level = conviction(pick.game_conviction_score)
  const isTotals = pick.market_type === "totals"
  const edgeDisplay = fmtPickSideEdge(pick)
  const edgeIsPos = !edgeDisplay.startsWith("-")

  return (
    <TableRow
      key={`${pick.game_pk}_${pick.market_type}`}
      className="cursor-pointer border-[#262626] bg-[#141414] hover:bg-[#1a1a1a] transition-colors"
      style={{ borderLeft: "2px solid #10b981" }}
      onClick={() => {
        posthog.capture("pick_clicked", {
          game_pk: pick.game_pk,
          market_type: pick.market_type,
          pick_side: pick.pick_side,
          conviction: conviction(pick.game_conviction_score),
        })
        router.push(`/picks/${pick.game_pk}`)
      }}
    >
      {/* Game */}
      <TableCell className="pl-4 py-4">
        <div className="font-semibold text-white text-sm whitespace-nowrap">
          {pick.away_team} @ {pick.home_team}
        </div>
        <div className="text-xs text-gray-500 mt-0.5">
          {fmtGameTime(pick.game_start_utc) ?? pick.game_date}
        </div>
        <div className="flex items-center gap-1 mt-1">
          <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${pick.lineup_confirmed ? "bg-[#10b981]" : "bg-[#f59e0b]"}`} />
          <span className={`text-[10px] font-medium ${pick.lineup_confirmed ? "text-[#10b981]" : "text-[#f59e0b]"}`}>
            {pick.lineup_confirmed ? "Confirmed" : "Projected"}
          </span>
        </div>
      </TableCell>

      {/* Pick side */}
      <TableCell className="py-4">
        <span className="text-sm font-semibold text-white whitespace-nowrap">
          {pickSideLabel(pick)}
        </span>
      </TableCell>

      {/* Model */}
      <TableCell className="py-4 text-right font-mono text-sm font-semibold text-[#10b981] whitespace-nowrap">
        {isTotals && pick.model_total_runs != null
          ? pick.model_total_runs.toFixed(1)
          : fmtPickSideProb(pick, pick.model_prob)}
      </TableCell>

      {/* Market / Line */}
      <TableCell className="py-4 text-right font-mono text-sm text-gray-400 whitespace-nowrap">
        {isTotals && pick.market_total_line != null
          ? pick.market_total_line.toFixed(1)
          : fmtPickSideProb(pick, pick.bovada_devig_prob)}
      </TableCell>

      {/* Edge */}
      <TableCell className="py-4 text-right font-mono text-sm font-semibold whitespace-nowrap">
        <span className={edgeIsPos ? "text-[#10b981]" : "text-[#ef4444]"}>{edgeDisplay}</span>
      </TableCell>

      {/* Conviction */}
      <TableCell className="py-4 text-center">
        <ConvictionBadge level={level} />
      </TableCell>

      {/* Bar — hidden on mobile */}
      <TableCell className="hidden md:table-cell py-4 pr-5 min-w-[180px]">
        {(() => {
          const flip = isSideFlipped(pick)
          const mProb = flip ? 1 - pick.model_prob : pick.model_prob
          const mkProb = flip ? 1 - pick.bovada_devig_prob : pick.bovada_devig_prob
          const ciLow = flip && pick.win_prob_ci_high != null ? 1 - pick.win_prob_ci_high : pick.win_prob_ci_low
          const ciHigh = flip && pick.win_prob_ci_low != null ? 1 - pick.win_prob_ci_low : pick.win_prob_ci_high
          return (
            <ProbabilityBar
              ciLow={ciLow}
              ciHigh={ciHigh}
              modelProb={mProb}
              marketProb={mkProb}
              showLabels={true}
              showCiLabels={false}
              showHighConviction={false}
            />
          )
        })()}
      </TableCell>
    </TableRow>
  )
}

function PickCard({ pick, router }: { pick: Pick; router: ReturnType<typeof useRouter> }) {
  const level = conviction(pick.game_conviction_score)
  const isTotals = pick.market_type === "totals"
  const edgeDisplay = fmtPickSideEdge(pick)
  const edgeIsPos = !edgeDisplay.startsWith("-")

  return (
    <div
      className="cursor-pointer rounded-xl border border-[#262626] bg-[#141414] p-4 transition-colors active:bg-[#10b98108]"
      style={{ borderLeft: "2px solid #10b981" }}
      onClick={() => {
        posthog.capture("pick_clicked", {
          game_pk: pick.game_pk,
          market_type: pick.market_type,
          pick_side: pick.pick_side,
          conviction: conviction(pick.game_conviction_score),
        })
        router.push(`/picks/${pick.game_pk}`)
      }}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-white">{pick.away_team} @ {pick.home_team}</p>
          <p className="text-xs text-gray-500 mt-0.5">{fmtGameTime(pick.game_start_utc) ?? pick.game_date}</p>
        </div>
        <ConvictionBadge level={level} />
      </div>
      <p className="mb-3 text-base font-bold text-white">{pickSideLabel(pick)}</p>
      <div className="grid grid-cols-3 gap-2">
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wide text-gray-600">
            {isTotals ? "Model Runs" : "Model Win%"}
          </p>
          <p className="mt-0.5 text-sm font-semibold text-[#10b981]">
            {isTotals && pick.model_total_runs != null
              ? pick.model_total_runs.toFixed(1)
              : fmtPickSideProb(pick, pick.model_prob)}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wide text-gray-600">
            {isTotals ? "O/U Line" : "Bovada%"}
          </p>
          <p className="mt-0.5 text-sm text-gray-400">
            {isTotals && pick.market_total_line != null
              ? pick.market_total_line.toFixed(1)
              : fmtPickSideProb(pick, pick.bovada_devig_prob)}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-medium uppercase tracking-wide text-gray-600">Edge</p>
          <p className={cn("mt-0.5 text-sm font-semibold", edgeIsPos ? "text-[#10b981]" : "text-[#ef4444]")}>
            {edgeDisplay}
          </p>
        </div>
      </div>
    </div>
  )
}

function PicksSection({
  title,
  picks,
  modelHeader,
  marketHeader,
  router,
}: {
  title: string
  picks: Pick[]
  modelHeader: string
  marketHeader: string
  router: ReturnType<typeof useRouter>
}) {
  if (picks.length === 0) return null
  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        <Badge className="bg-[#10b981] text-[#0a0a0a] text-xs font-bold px-2 py-0.5">
          {picks.length}
        </Badge>
      </div>

      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto rounded-xl border border-[#262626]">
        <Table>
          <TableHeader>
            <TableRow className="border-[#262626] hover:bg-transparent">
              <TableHead className={`${TH} pl-5`}>Game</TableHead>
              <TableHead className={TH}>Pick</TableHead>
              <TableHead className={`${TH} text-right`}>{modelHeader}</TableHead>
              <TableHead className={`${TH} text-right`}>{marketHeader}</TableHead>
              <TableHead className={`${TH} text-right`}>Edge</TableHead>
              <TableHead className={`${TH} text-center`}>Conviction</TableHead>
              <TableHead className={`${TH} hidden md:table-cell min-w-[180px] text-center`}>Bar</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {picks.map((pick) => (
              <PickRow key={`${pick.game_pk}_${pick.market_type}`} pick={pick} router={router} />
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Mobile cards */}
      <div className="md:hidden space-y-3">
        {picks.map((pick) => (
          <PickCard key={`${pick.game_pk}_${pick.market_type}`} pick={pick} router={router} />
        ))}
      </div>
    </div>
  )
}

function SkeletonTable() {
  return (
    <div className="overflow-x-auto rounded-xl border border-[#262626]">
      <Table>
        <TableHeader>
          <TableRow className="border-[#262626] hover:bg-transparent">
            <TableHead className={`${TH} pl-5`}>Game</TableHead>
            <TableHead className={TH}>Pick</TableHead>
            <TableHead className={`${TH} text-right`}>Model</TableHead>
            <TableHead className={`${TH} text-right`}>Line</TableHead>
            <TableHead className={`${TH} text-right`}>Edge</TableHead>
            <TableHead className={`${TH} text-center`}>Conviction</TableHead>
            <TableHead className={`${TH} hidden md:table-cell min-w-[180px] text-center`}>Bar</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {[0, 1, 2].map((i) => (
            <TableRow key={i} className="border-[#262626] bg-[#141414]">
              <TableCell className="pl-4 py-4"><Skeleton className="h-4 w-28" /></TableCell>
              <TableCell className="py-4"><Skeleton className="h-4 w-12" /></TableCell>
              <TableCell className="py-4 text-right"><Skeleton className="h-4 w-12 ml-auto" /></TableCell>
              <TableCell className="py-4 text-right"><Skeleton className="h-4 w-12 ml-auto" /></TableCell>
              <TableCell className="py-4 text-right"><Skeleton className="h-4 w-12 ml-auto" /></TableCell>
              <TableCell className="py-4 text-center"><Skeleton className="h-5 w-12 mx-auto rounded-full" /></TableCell>
              <TableCell className="hidden md:table-cell py-4 pr-5"><Skeleton className="h-4 w-full" /></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function QualifiedPicksTable({
  picks,
  isLoading,
  isError,
}: {
  picks: Pick[]
  isLoading: boolean
  isError: boolean
}) {
  const router = useRouter()

  if (isLoading) {
    return (
      <div className="mx-auto max-w-6xl px-4 flex flex-col gap-8">
        {[3, 2].map((count, idx) => (
          <div key={idx}>
            <div className="mb-3 h-5 w-32 animate-pulse rounded bg-[#262626]" />
            <div className="hidden md:block"><SkeletonTable /></div>
            <div className="md:hidden space-y-3">
              {Array.from({ length: count }).map((_, i) => (
                <div key={i} className="rounded-xl border border-[#262626] bg-[#141414] p-4 space-y-3">
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="h-5 w-20" />
                  <div className="grid grid-cols-3 gap-2 pt-1">
                    <Skeleton className="h-10 rounded-lg" />
                    <Skeleton className="h-10 rounded-lg" />
                    <Skeleton className="h-10 rounded-lg" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="mx-auto max-w-6xl px-4">
        <div className="flex flex-col items-center justify-center rounded-xl border border-[#262626] bg-[#141414] py-16 text-center">
          <TrendingUp className="h-10 w-10 text-gray-700 mb-4" />
          <h3 className="text-base font-semibold text-white">Unable to load picks</h3>
          <p className="mt-2 max-w-sm text-sm leading-relaxed text-gray-500">
            Could not reach the predictions API. Try refreshing the page.
          </p>
        </div>
      </div>
    )
  }

  if (picks.length === 0) {
    return (
      <div className="mx-auto max-w-6xl px-4">
        <div className="flex flex-col items-center justify-center rounded-xl border border-[#262626] bg-[#141414] py-16 text-center">
          <TrendingUp className="h-10 w-10 text-gray-700 mb-4" />
          <h3 className="text-base font-semibold text-white">No qualified picks for today</h3>
          <p className="mt-2 max-w-sm text-sm leading-relaxed text-gray-500">
            Check back after the morning pipeline completes, or once lineups are confirmed.
          </p>
        </div>
      </div>
    )
  }

  const h2hPicks = picks.filter((p) => p.market_type === "h2h")
  const totalsPicks = picks.filter((p) => p.market_type === "totals")

  return (
    <div className="mx-auto max-w-6xl px-4">
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-base font-semibold text-white">Today&apos;s Picks</h2>
        <Badge className="bg-[#10b981] text-[#0a0a0a] text-xs font-bold px-2 py-0.5">
          {picks.length}
        </Badge>
      </div>

      <div className="flex flex-col gap-8">
        <PicksSection
          title="Moneyline"
          picks={h2hPicks}
          modelHeader="Model Win %"
          marketHeader="Bovada Win %"
          router={router}
        />
        <PicksSection
          title="Total Runs"
          picks={totalsPicks}
          modelHeader="Model Runs"
          marketHeader="O/U Line"
          router={router}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const { accessToken, email } = useAuth()
  const { selectedDate, setSelectedDate, isoDate, isToday } = useSelectedDate()
  const [calOpen, setCalOpen] = useState(false)
  const todayIso = format(new Date(), "yyyy-MM-dd")

  const { data: todayData, isLoading: todayLoading, isError: todayError } = useQuery({
    queryKey: ["picks-today", accessToken, todayIso],
    queryFn: () => apiFetch(`/picks/today?date=${todayIso}`, {}, accessToken),
    staleTime: 5 * 60 * 1000,
    enabled: !!accessToken && isToday,
  })

  const { data: evData, isLoading: evLoading, isError: evError } = useQuery({
    queryKey: ["picks-ev", isoDate, accessToken],
    queryFn: () => apiFetch(`/picks/ev?date=${isoDate}`, {}, accessToken),
    staleTime: 5 * 60 * 1000,
    enabled: !!accessToken && !isToday,
  })

  const isLoading = isToday ? todayLoading : evLoading
  const isError = isToday ? todayError : evError
  const picks: Pick[] = isToday
    ? (todayData?.picks ?? []).map((p: Pick) => ({
        ...p,
        home_team: normalizeTeam(p.home_team),
        away_team: normalizeTeam(p.away_team),
      }))
    : (evData?.picks ?? []).filter((p: any) => p.qualified_bet === true).map(normalizeEVPick)

  const datePicker = (
    <Popover open={calOpen} onOpenChange={setCalOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className="h-8 justify-start gap-2 border-[#262626] bg-[#141414] text-left text-sm font-normal text-gray-400 hover:bg-[#1a1a1a] hover:text-white"
        >
          <CalendarIcon className="h-3.5 w-3.5 text-gray-500" />
          {isToday ? "Today" : format(selectedDate, "MMM d, yyyy")}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto border-[#262626] bg-[#141414] p-0" align="end">
        <Calendar
          mode="single"
          selected={selectedDate}
          onSelect={(d) => { if (d) { setSelectedDate(d); setCalOpen(false); posthog.capture("dashboard_date_changed", { date: format(d, "yyyy-MM-dd") }) } }}
          toDate={new Date()}
          initialFocus
        />
      </PopoverContent>
    </Popover>
  )

  const isPreliminary = isToday && !isLoading && (todayData?.is_preliminary === true)

  return (
    <AuthGuard>
      <div className="min-h-screen bg-[#0a0a0a] font-sans">
        <Nav authenticated activeLink="dashboard" userEmail={email} />
        <main className="pb-16">
          <PageHeader picks={picks} isLoading={isLoading} rightSlot={datePicker} />
          {isPreliminary && (
            <div className="mx-auto max-w-6xl px-4 mt-3">
              <div className="flex items-start gap-2.5 rounded-lg border border-amber-800 bg-amber-950 px-4 py-3 text-sm text-amber-300">
                <span className="mt-0.5 shrink-0 font-bold">⚠</span>
                <span>
                  <span className="font-semibold">Preliminary predictions</span> — lineups not yet confirmed.
                  These picks are based on probable pitchers only. Do not bet until confirmed lineups are posted (~90 min before first pitch).
                </span>
              </div>
            </div>
          )}
          <div className="mt-6">
            <QualifiedPicksTable picks={picks} isLoading={isLoading} isError={isError} />
          </div>
        </main>
      </div>
    </AuthGuard>
  )
}
