"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { ProbabilityBar } from "@/components/probability-bar"
import { PipelineStatusDot } from "@/components/pipeline-status-dot"
import { ChevronDown, Info, LogOut, TrendingUp } from "lucide-react"

// ---------------------------------------------------------------------------
// TODO: replace with useQuery hook — GET /picks/today
// ---------------------------------------------------------------------------
const MOCK_DATA = {
  date: "Friday, June 5, 2026",
  qualifiedPicks: [
    {
      game_pk: 1001,
      game: "HOU @ NYM",
      time: "7:10 PM ET",
      minutesUntilFirstPitch: 134,
      market: "Totals Over 8.5",
      marketType: "total",
      modelProb: 0.583,
      marketProb: 0.541,
      edge: 0.042,
      conviction: "HIGH",
      ciLow: 0.48,
      ciHigh: 0.61,
    },
    {
      game_pk: 1002,
      game: "LAD @ SF",
      time: "9:45 PM ET",
      minutesUntilFirstPitch: 349,
      market: "Home ML",
      marketType: "moneyline",
      modelProb: 0.612,
      marketProb: 0.571,
      edge: 0.041,
      conviction: "MED",
      ciLow: 0.54,
      ciHigh: 0.68,
    },
    {
      game_pk: 1003,
      game: "ATL @ PHI",
      time: "7:05 PM ET",
      minutesUntilFirstPitch: 25,
      market: "Away ML",
      marketType: "moneyline",
      modelProb: 0.534,
      marketProb: 0.502,
      edge: 0.032,
      conviction: "LOW",
      ciLow: 0.49,
      ciHigh: 0.58,
    },
  ],
  nonQualifiedGames: [
    {
      game_pk: 1004,
      game: "NYY @ BOS",
      time: "7:10 PM ET",
      market: "Totals Under 8.0",
      marketType: "total",
      modelProb: 0.481,
      marketProb: 0.51,
      edge: -0.029,
    },
    {
      game_pk: 1005,
      game: "CHC @ MIL",
      time: "8:10 PM ET",
      market: "Home ML",
      marketType: "moneyline",
      modelProb: 0.523,
      marketProb: 0.541,
      edge: -0.018,
    },
    {
      game_pk: 1006,
      game: "SEA @ TEX",
      time: "8:05 PM ET",
      market: "Totals Over 7.5",
      marketType: "total",
      modelProb: 0.498,
      marketProb: 0.512,
      edge: -0.014,
    },
  ],
  signalFreshness: {
    lastUpdated: "Today 8:14 AM EDT",
    status: "fresh" as "fresh" | "stale" | "missing",
  },
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(val: number) {
  return `${(val * 100).toFixed(1)}%`
}

function formatCountdown(minutes: number): string {
  if (minutes < 60) return `${minutes}m`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m === 0 ? `${h}h` : `${h}h ${m}m`
}

function MarketBadge({ market, type }: { market: string; type: string }) {
  if (type === "total") {
    return (
      <Badge className="bg-teal-500/10 text-teal-400 border border-teal-500/20 text-xs font-medium whitespace-nowrap">
        {market}
      </Badge>
    )
  }
  return (
    <Badge className="bg-blue-500/10 text-blue-400 border border-blue-500/20 text-xs font-medium whitespace-nowrap">
      {market}
    </Badge>
  )
}

function ConvictionBadge({ conviction }: { conviction: string }) {
  if (conviction === "HIGH") {
    return (
      <Badge className="bg-[#10b981] text-[#0a0a0a] text-xs font-bold uppercase tracking-widest">
        HIGH
      </Badge>
    )
  }
  if (conviction === "MED") {
    return (
      <Badge
        variant="outline"
        className="border-[#f59e0b] text-[#f59e0b] text-xs font-bold uppercase tracking-widest"
      >
        MED
      </Badge>
    )
  }
  return (
    <Badge
      variant="outline"
      className="border-gray-600 text-gray-500 text-xs font-bold uppercase tracking-widest"
    >
      LOW
    </Badge>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Navbar() {
  return (
    <nav className="sticky top-0 z-50 border-b border-[#262626] bg-[#0a0a0a]/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        <Link
          href="/"
          className="flex items-center gap-0 text-lg font-bold tracking-tight"
        >
          <span className="text-[#10b981]">Credence</span>
          <span className="text-white"> Sports</span>
        </Link>
        <div className="flex items-center gap-3">
          <span className="hidden text-xs text-gray-500 sm:block">
            user@example.com
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="text-gray-400 hover:text-white hover:bg-[#141414]"
            asChild
          >
            <Link href="/">
              <LogOut className="mr-1.5 h-3.5 w-3.5" />
              Sign Out
            </Link>
          </Button>
        </div>
      </div>
      {/* Sub-nav */}
      <div className="mx-auto flex max-w-6xl gap-6 px-4 pb-0">
        <Link
          href="/dashboard"
          className="border-b-2 border-[#10b981] pb-2.5 text-sm text-white font-medium transition-colors"
        >
          Dashboard
        </Link>
        <Link
          href="/performance"
          className="border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
        >
          Performance
        </Link>
        <Link
          href="/settings"
          className="border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
        >
          Settings
        </Link>
      </div>
    </nav>
  )
}

function PageHeader({
  date,
  qualifiedCount,
  totalGames,
}: {
  date: string
  qualifiedCount: number
  totalGames: number
}) {
  return (
    <div className="mx-auto max-w-6xl px-4 pt-10 pb-6">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
        <h1 className="text-3xl font-bold tracking-tight text-white md:text-4xl">
          Dashboard
        </h1>
        <span className="text-sm text-gray-500">{date}</span>
      </div>
      <p className="mt-2 text-sm text-gray-400">
        <span className="font-semibold text-[#10b981]">{qualifiedCount} qualified picks</span>
        <span className="text-gray-600"> &middot; </span>
        <span>{totalGames} total games today</span>
      </p>
      {/* A1.4 — live pipeline freshness indicator (green/yellow/red) */}
      <div className="mt-3">
        <PipelineStatusDot />
      </div>
    </div>
  )
}

function SignalFreshness({
  freshness,
}: {
  freshness: typeof MOCK_DATA.signalFreshness
}) {
  const dotColor =
    freshness.status === "fresh"
      ? "bg-[#10b981]"
      : freshness.status === "stale"
      ? "bg-[#f59e0b]"
      : "bg-[#ef4444]"

  return (
    <div className="mx-auto max-w-6xl px-4 pt-4 pb-2">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${dotColor} shrink-0`} />
        <span className="text-xs text-gray-500">
          Signals last updated:{" "}
          <span className="text-gray-400">{freshness.lastUpdated}</span>
        </span>
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Info className="h-3 w-3 text-gray-600 cursor-default" />
            </TooltipTrigger>
            <TooltipContent
              side="right"
              className="max-w-xs bg-[#141414] border-[#262626] text-gray-300 text-xs leading-relaxed"
            >
              Signals are generated each morning after lineup confirmation.
              Predictions update again after lineups are confirmed ~90 minutes
              before first pitch.
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    </div>
  )
}

function QualifiedPicksTable() {
  const router = useRouter()
  const picks = MOCK_DATA.qualifiedPicks

  if (picks.length === 0) {
    return (
      <div className="mx-auto max-w-6xl px-4">
        <div className="flex flex-col items-center justify-center rounded-xl border border-[#262626] bg-[#141414] py-16 text-center">
          <TrendingUp className="h-10 w-10 text-gray-700 mb-4" />
          <h3 className="text-base font-semibold text-white">
            No qualified picks today
          </h3>
          <p className="mt-2 max-w-sm text-sm leading-relaxed text-gray-500">
            The model found no edges that clear all gate criteria for
            today&apos;s games.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-6xl px-4">
      {/* Section heading */}
      <div className="mb-4 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold text-white">Today&apos;s Picks</h2>
          <Badge className="bg-[#10b981] text-[#0a0a0a] text-xs font-bold px-2 py-0.5">
            {picks.length}
          </Badge>
        </div>
        <Link
          href="/ev-tracker"
          className="text-xs font-medium text-[#10b981] hover:text-[#059669] transition-colors"
        >
          EV Tracker &rarr;
        </Link>
      </div>

      {/* Scrollable table wrapper */}
      <div className="overflow-x-auto rounded-xl border border-[#262626]">
        <Table>
          <TableHeader>
            <TableRow className="border-[#262626] hover:bg-transparent">
              <TableHead className="text-xs uppercase tracking-wider text-gray-500 font-medium pl-5">
                Game
              </TableHead>
              <TableHead className="text-xs uppercase tracking-wider text-gray-500 font-medium">
                Market
              </TableHead>
              <TableHead className="text-xs uppercase tracking-wider text-gray-500 font-medium text-right">
                Model
              </TableHead>
              <TableHead className="text-xs uppercase tracking-wider text-gray-500 font-medium text-right">
                Market
              </TableHead>
              <TableHead className="text-xs uppercase tracking-wider text-gray-500 font-medium text-right">
                Edge
              </TableHead>
              <TableHead className="text-xs uppercase tracking-wider text-gray-500 font-medium">
                Conviction
              </TableHead>
              <TableHead className="text-xs uppercase tracking-wider text-gray-500 font-medium text-right">
                Time
              </TableHead>
              <TableHead className="hidden md:table-cell text-xs uppercase tracking-wider text-gray-500 font-medium min-w-[160px]">
                Bar
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {picks.map((pick) => {
              const timeIsUrgent = pick.minutesUntilFirstPitch < 30
              return (
                <TableRow
                  key={pick.game_pk}
                  className="cursor-pointer border-[#262626] bg-[#141414] hover:bg-[#1a1a1a] transition-colors"
                  style={{ borderLeft: "2px solid #10b981" }}
                  onClick={() => router.push(`/picks/${pick.game_pk}`)}
                >
                  {/* Game */}
                  <TableCell className="pl-4 py-4">
                    <div className="font-semibold text-white text-sm whitespace-nowrap">
                      {pick.game}
                    </div>
                    <div className="text-xs text-gray-500 mt-0.5">
                      {pick.time}
                    </div>
                  </TableCell>

                  {/* Market */}
                  <TableCell className="py-4">
                    <MarketBadge market={pick.market} type={pick.marketType} />
                  </TableCell>

                  {/* Model prob */}
                  <TableCell className="py-4 text-right font-mono text-sm font-semibold text-[#10b981] whitespace-nowrap">
                    {fmt(pick.modelProb)}
                  </TableCell>

                  {/* Market prob */}
                  <TableCell className="py-4 text-right font-mono text-sm text-gray-400 whitespace-nowrap">
                    {fmt(pick.marketProb)}
                  </TableCell>

                  {/* Edge */}
                  <TableCell className="py-4 text-right font-mono text-sm font-semibold whitespace-nowrap">
                    <span
                      className={
                        pick.edge >= 0 ? "text-[#10b981]" : "text-[#ef4444]"
                      }
                    >
                      {pick.edge >= 0 ? "+" : ""}
                      {(pick.edge * 100).toFixed(1)}%
                    </span>
                  </TableCell>

                  {/* Conviction */}
                  <TableCell className="py-4">
                    <ConvictionBadge conviction={pick.conviction} />
                  </TableCell>

                  {/* Time */}
                  <TableCell className="py-4 text-right font-mono text-sm whitespace-nowrap">
                    <span
                      className={
                        timeIsUrgent ? "text-[#ef4444]" : "text-gray-400"
                      }
                    >
                      {formatCountdown(pick.minutesUntilFirstPitch)}
                    </span>
                  </TableCell>

                  {/* Bar — compact, hidden on mobile */}
                  <TableCell className="hidden md:table-cell py-4 pr-5 min-w-[160px]">
                    <ProbabilityBar
                      ciLow={pick.ciLow}
                      ciHigh={pick.ciHigh}
                      modelProb={pick.modelProb}
                      marketProb={pick.marketProb}
                      showLabels={false}
                      showHighConviction={false}
                    />
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

function NonQualifiedSection() {
  const [isOpen, setIsOpen] = useState(false)
  const games = MOCK_DATA.nonQualifiedGames

  return (
    <div className="mx-auto max-w-6xl px-4">
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CollapsibleTrigger className="flex w-full items-center gap-2 text-left">
          <span className="text-sm text-gray-500">
            Non-Qualified Games ({games.length})
          </span>
          <ChevronDown
            className={`h-4 w-4 text-gray-600 transition-transform duration-200 ${
              isOpen ? "rotate-180" : ""
            }`}
          />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="mt-3 overflow-x-auto rounded-xl border border-[#262626] opacity-50">
            <Table>
              <TableHeader>
                <TableRow className="border-[#262626] hover:bg-transparent">
                  <TableHead className="text-xs uppercase tracking-wider text-gray-500 font-medium pl-5">
                    Game
                  </TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-gray-500 font-medium">
                    Market
                  </TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-gray-500 font-medium text-right">
                    Model
                  </TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-gray-500 font-medium text-right">
                    Market
                  </TableHead>
                  <TableHead className="text-xs uppercase tracking-wider text-gray-500 font-medium text-right">
                    Edge
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {games.map((game) => (
                  <TableRow
                    key={game.game_pk}
                    className="border-[#262626] bg-[#141414]"
                  >
                    <TableCell className="pl-4 py-3">
                      <div className="font-semibold text-white text-sm whitespace-nowrap">
                        {game.game}
                      </div>
                      <div className="text-xs text-gray-500 mt-0.5">
                        {game.time}
                      </div>
                    </TableCell>
                    <TableCell className="py-3">
                      <MarketBadge market={game.market} type={game.marketType} />
                    </TableCell>
                    <TableCell className="py-3 text-right font-mono text-sm text-gray-400 whitespace-nowrap">
                      {fmt(game.modelProb)}
                    </TableCell>
                    <TableCell className="py-3 text-right font-mono text-sm text-gray-400 whitespace-nowrap">
                      {fmt(game.marketProb)}
                    </TableCell>
                    <TableCell className="py-3 text-right font-mono text-sm font-semibold text-[#ef4444] whitespace-nowrap">
                      {(game.edge * 100).toFixed(1)}%
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const qualifiedCount = MOCK_DATA.qualifiedPicks.length
  const totalGames =
    MOCK_DATA.qualifiedPicks.length + MOCK_DATA.nonQualifiedGames.length

  return (
    <div className="min-h-screen bg-[#0a0a0a] font-sans">
      <Navbar />
      <main className="pb-16">
        <PageHeader
          date={MOCK_DATA.date}
          qualifiedCount={qualifiedCount}
          totalGames={totalGames}
        />
        <SignalFreshness freshness={MOCK_DATA.signalFreshness} />
        <div className="mt-6 flex flex-col gap-8">
          <QualifiedPicksTable />
          <NonQualifiedSection />
        </div>
      </main>
    </div>
  )
}
