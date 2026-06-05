"use client"

import { useState } from "react"
import Link from "next/link"
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts"
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { LogOut } from "lucide-react"

// ---------------------------------------------------------------------------
// TODO: replace with useQuery hooks — GET /performance/summary and GET /performance/by-model
// ---------------------------------------------------------------------------
const MOCK_DATA = {
  summary: {
    totalBets: 247,
    winRate: 0.543,
    meanCLV: 0.021,
    netPnlFlat: 312,
    netPnlKelly: 428,
    netPnlPortfolioKelly: 391,
  },
  plCurveFlat: [
    { date: "Apr 12", pnl: 0 },
    { date: "Apr 19", pnl: 42 },
    { date: "Apr 26", pnl: 18 },
    { date: "May 1", pnl: 31 },
    { date: "May 10", pnl: 89 },
    { date: "May 17", pnl: 156 },
    { date: "May 24", pnl: 203 },
    { date: "May 31", pnl: 271 },
    { date: "Jun 5", pnl: 312 },
  ],
  byMarket: [
    { market: "Totals Over", bets: 89, winRate: 0.562, meanCLV: 0.031, netPnl: 147 },
    { market: "Totals Under", bets: 67, winRate: 0.537, meanCLV: 0.018, netPnl: 84 },
    { market: "Home ML", bets: 54, winRate: 0.519, meanCLV: 0.011, netPnl: 52 },
    { market: "Away ML", bets: 37, winRate: 0.541, meanCLV: 0.024, netPnl: 29 },
  ],
  byConviction: [
    { tier: "HIGH", bets: 43, winRate: 0.581, meanCLV: 0.038, netPnl: 187 },
    { tier: "MED", bets: 98, winRate: 0.531, meanCLV: 0.014, netPnl: 89 },
    { tier: "LOW", bets: 106, winRate: 0.510, meanCLV: -0.003, netPnl: -24 },
  ],
  bySignal: [
    { signal: "Run Environment", bets: 71, winRate: 0.563, meanCLV: 0.029, netPnl: 118 },
    { signal: "Starter Quality", bets: 89, winRate: 0.551, meanCLV: 0.024, netPnl: 143 },
    { signal: "Offense Advantage", bets: 43, winRate: 0.512, meanCLV: 0.008, netPnl: 31 },
    { signal: "Bullpen State", bets: 28, winRate: 0.536, meanCLV: 0.019, netPnl: 38 },
    { signal: "Matchup", bets: 16, winRate: 0.500, meanCLV: 0.001, netPnl: -18 },
  ],
  recentResults: [
    { date: "Jun 4", game: "NYY @ BOS", market: "Totals Under 8.0", side: "Under", modelProb: 0.531, bovadaProb: 0.510, edge: 0.021, result: "Won", clv: 0.018 },
    { date: "Jun 4", game: "LAD @ SF", market: "Home ML", side: "LAD", modelProb: 0.612, bovadaProb: 0.571, edge: 0.041, result: "Lost", clv: 0.033 },
    { date: "Jun 3", game: "HOU @ NYM", market: "Totals Over 8.5", side: "Over", modelProb: 0.583, bovadaProb: 0.541, edge: 0.042, result: "Won", clv: 0.038 },
    { date: "Jun 3", game: "ATL @ PHI", market: "Away ML", side: "ATL", modelProb: 0.534, bovadaProb: 0.502, edge: 0.032, result: "Won", clv: 0.021 },
    { date: "Jun 2", game: "CHC @ MIL", market: "Totals Over 7.5", side: "Over", modelProb: 0.521, bovadaProb: 0.498, edge: 0.023, result: "Lost", clv: -0.011 },
    { date: "Jun 1", game: "SEA @ TEX", market: "Home ML", side: "TEX", modelProb: 0.548, bovadaProb: 0.519, edge: 0.029, result: "Push", clv: 0.014 },
    { date: "Jun 1", game: "NYM @ WSH", market: "Totals Under 7.0", side: "Under", modelProb: 0.562, bovadaProb: 0.531, edge: 0.031, result: "Won", clv: 0.027 },
    { date: "May 31", game: "BOS @ TOR", market: "Away ML", side: "BOS", modelProb: 0.541, bovadaProb: 0.512, edge: 0.029, result: "Won", clv: 0.019 },
    { date: "May 31", game: "MIN @ CLE", market: "Totals Over 8.0", side: "Over", modelProb: 0.519, bovadaProb: 0.501, edge: 0.018, result: "Lost", clv: -0.004 },
    { date: "May 30", game: "SF @ COL", market: "Away ML", side: "SF", modelProb: 0.571, bovadaProb: 0.538, edge: 0.033, result: "Won", clv: 0.029 },
  ],
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type SizingMethod = "Flat" | "Kelly" | "Portfolio Kelly"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtPct(val: number) {
  return `${(val * 100).toFixed(1)}%`
}

function fmtPnl(val: number) {
  return val >= 0 ? `+$${val}` : `-$${Math.abs(val)}`
}

function clvColor(val: number) {
  return val >= 0 ? "text-[#10b981]" : "text-[#ef4444]"
}

function pnlColor(val: number) {
  return val >= 0 ? "text-[#10b981]" : "text-[#ef4444]"
}

function winRateColor(val: number) {
  if (val > 0.52) return "text-[#10b981]"
  if (val >= 0.50) return "text-[#f59e0b]"
  return "text-[#ef4444]"
}

function deriveKellySeries(flat: typeof MOCK_DATA.plCurveFlat, multiplier: number) {
  return flat.map((d) => ({ date: d.date, pnl: Math.round(d.pnl * multiplier) }))
}

// ---------------------------------------------------------------------------
// Sparkline — simple SVG polyline for stat tiles
// ---------------------------------------------------------------------------

function Sparkline({ data, color }: { data: number[]; color: string }) {
  const w = 80
  const h = 28
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const pts = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * w
      const y = h - ((v - min) / range) * h
      return `${x},${y}`
    })
    .join(" ")

  return (
    <svg width={w} height={h} className="overflow-visible">
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity={0.7}
      />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Conviction badge (matches dashboard style exactly)
// ---------------------------------------------------------------------------

function ConvictionBadge({ tier }: { tier: string }) {
  if (tier === "HIGH") {
    return (
      <Badge className="bg-[#10b981] text-[#0a0a0a] text-xs font-bold uppercase tracking-widest">
        HIGH
      </Badge>
    )
  }
  if (tier === "MED") {
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
// Result badge
// ---------------------------------------------------------------------------

function ResultBadge({ result }: { result: string }) {
  if (result === "Won") {
    return (
      <Badge className="bg-[#10b981]/15 text-[#10b981] border border-[#10b981]/30 text-xs font-semibold">
        Won
      </Badge>
    )
  }
  if (result === "Lost") {
    return (
      <Badge className="bg-[#ef4444]/15 text-[#ef4444] border border-[#ef4444]/30 text-xs font-semibold">
        Lost
      </Badge>
    )
  }
  return (
    <Badge
      variant="outline"
      className="border-gray-600 text-gray-500 text-xs font-semibold"
    >
      Push
    </Badge>
  )
}

// ---------------------------------------------------------------------------
// Custom recharts tooltip
// ---------------------------------------------------------------------------

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  const val = payload[0].value as number
  return (
    <div className="rounded-lg border border-[#262626] bg-[#141414] px-3 py-2 shadow-xl">
      <p className="text-xs text-gray-400 mb-1">{label}</p>
      <p className={`text-sm font-semibold font-mono ${pnlColor(val)}`}>
        {fmtPnl(val)}
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Navbar
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
          className="border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
        >
          Dashboard
        </Link>
        <Link
          href="/performance"
          className="border-b-2 border-[#10b981] pb-2.5 text-sm text-white font-medium transition-colors"
        >
          Performance
        </Link>
      </div>
    </nav>
  )
}

// ---------------------------------------------------------------------------
// Stat tiles
// ---------------------------------------------------------------------------

function StatTiles({
  sizing,
}: {
  sizing: SizingMethod
}) {
  const { summary } = MOCK_DATA
  const netPnl =
    sizing === "Flat"
      ? summary.netPnlFlat
      : sizing === "Kelly"
      ? summary.netPnlKelly
      : summary.netPnlPortfolioKelly

  // Sparkline data — derived from plCurveFlat counts/rates
  const betCountSpark = [12, 28, 41, 67, 103, 148, 191, 224, 247]
  const winRateSpark = [0.50, 0.52, 0.49, 0.53, 0.55, 0.54, 0.543, 0.542, 0.543]
  const clvSpark = [0.008, 0.012, 0.009, 0.018, 0.021, 0.019, 0.022, 0.020, 0.021]
  const pnlSpark = MOCK_DATA.plCurveFlat.map((d) => d.pnl)

  const tiles = [
    {
      label: "Total Bets",
      value: summary.totalBets.toString(),
      valueClass: "text-white",
      spark: betCountSpark,
      sparkColor: "#6b7280",
    },
    {
      label: "Win Rate",
      value: fmtPct(summary.winRate),
      valueClass: winRateColor(summary.winRate),
      spark: winRateSpark,
      sparkColor: winRateColor(summary.winRate) === "text-[#10b981]" ? "#10b981" : winRateColor(summary.winRate) === "text-[#f59e0b]" ? "#f59e0b" : "#ef4444",
    },
    {
      label: "Mean CLV",
      value: `+${fmtPct(summary.meanCLV)}`,
      valueClass: clvColor(summary.meanCLV),
      spark: clvSpark,
      sparkColor: "#10b981",
    },
    {
      label: `Net P&L (${sizing})`,
      value: fmtPnl(netPnl),
      valueClass: pnlColor(netPnl),
      spark: pnlSpark,
      sparkColor: netPnl >= 0 ? "#10b981" : "#ef4444",
    },
  ]

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {tiles.map((tile) => (
        <div
          key={tile.label}
          className="flex flex-col justify-between rounded-xl border border-[#262626] bg-[#141414] px-5 py-4"
        >
          <div className="flex items-start justify-between gap-2">
            <p className="text-xs uppercase tracking-wider text-gray-500 font-medium leading-relaxed">
              {tile.label}
            </p>
            <Sparkline data={tile.spark} color={tile.sparkColor} />
          </div>
          <p className={`mt-3 text-3xl font-bold tracking-tight font-mono ${tile.valueClass}`}>
            {tile.value}
          </p>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// P&L Curve
// ---------------------------------------------------------------------------

function PLCurve({ sizing }: { sizing: SizingMethod }) {
  const flat = MOCK_DATA.plCurveFlat
  const data =
    sizing === "Flat"
      ? flat
      : sizing === "Kelly"
      ? deriveKellySeries(flat, 1.37)
      : deriveKellySeries(flat, 1.25)

  return (
    <div className="rounded-xl border border-[#262626] bg-[#141414] px-5 pt-5 pb-4">
      <h2 className="mb-4 text-sm font-semibold text-white">
        Cumulative P&amp;L — {sizing}
      </h2>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#262626" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: "#6b7280", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            dy={6}
          />
          <YAxis
            tick={{ fill: "#6b7280", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => `$${v}`}
            width={44}
          />
          <Tooltip content={<ChartTooltip />} />
          {/* Zero baseline */}
          <ReferenceLine y={0} stroke="#374151" strokeDasharray="4 3" />
          {/* Layer 3 live annotation */}
          <ReferenceLine
            x="May 1"
            stroke="#f59e0b"
            strokeDasharray="4 3"
            label={{
              value: "Layer 3 live",
              position: "insideTopRight",
              fill: "#f59e0b",
              fontSize: 10,
              dy: -4,
            }}
          />
          <Line
            type="monotone"
            dataKey="pnl"
            stroke="#10b981"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: "#10b981", stroke: "#0a0a0a", strokeWidth: 2 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Breakdown tabs
// ---------------------------------------------------------------------------

const thClass = "text-xs uppercase tracking-wider text-gray-500 font-medium"
const tdBase = "py-3 font-mono text-sm"

function ByMarketTable() {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="border-[#262626] hover:bg-transparent">
            <TableHead className={`${thClass} pl-0`}>Market Type</TableHead>
            <TableHead className={`${thClass} text-right`}>Bets</TableHead>
            <TableHead className={`${thClass} text-right`}>Win Rate</TableHead>
            <TableHead className={`${thClass} text-right`}>Mean CLV</TableHead>
            <TableHead className={`${thClass} text-right`}>Net P&L</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {MOCK_DATA.byMarket.map((row) => (
            <TableRow key={row.market} className="border-[#262626] hover:bg-[#1a1a1a]">
              <TableCell className="py-3 text-sm text-gray-300 pl-0">{row.market}</TableCell>
              <TableCell className={`${tdBase} text-right text-gray-400`}>{row.bets}</TableCell>
              <TableCell className={`${tdBase} text-right ${winRateColor(row.winRate)}`}>{fmtPct(row.winRate)}</TableCell>
              <TableCell className={`${tdBase} text-right ${clvColor(row.meanCLV)}`}>{row.meanCLV >= 0 ? "+" : ""}{fmtPct(row.meanCLV)}</TableCell>
              <TableCell className={`${tdBase} text-right ${pnlColor(row.netPnl)}`}>{fmtPnl(row.netPnl)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function ByConvictionTable() {
  return (
    <div>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="border-[#262626] hover:bg-transparent">
              <TableHead className={`${thClass} pl-0`}>Conviction</TableHead>
              <TableHead className={`${thClass} text-right`}>Bets</TableHead>
              <TableHead className={`${thClass} text-right`}>Win Rate</TableHead>
              <TableHead className={`${thClass} text-right`}>Mean CLV</TableHead>
              <TableHead className={`${thClass} text-right`}>Net P&L</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {MOCK_DATA.byConviction.map((row) => (
              <TableRow key={row.tier} className="border-[#262626] hover:bg-[#1a1a1a]">
                <TableCell className="py-3 pl-0">
                  <ConvictionBadge tier={row.tier} />
                </TableCell>
                <TableCell className={`${tdBase} text-right text-gray-400`}>{row.bets}</TableCell>
                <TableCell className={`${tdBase} text-right ${winRateColor(row.winRate)}`}>{fmtPct(row.winRate)}</TableCell>
                <TableCell className={`${tdBase} text-right ${clvColor(row.meanCLV)}`}>{row.meanCLV >= 0 ? "+" : ""}{fmtPct(row.meanCLV)}</TableCell>
                <TableCell className={`${tdBase} text-right ${pnlColor(row.netPnl)}`}>{fmtPnl(row.netPnl)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <p className="mt-4 text-xs leading-relaxed text-gray-600">
        Conviction tiers reflect the model&apos;s gate criteria score at prediction time. HIGH = all 5 gates fired. MED = 4 gates. LOW = 3 gates.
      </p>
    </div>
  )
}

function BySignalTable() {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="border-[#262626] hover:bg-transparent">
            <TableHead className={`${thClass} pl-0`}>Signal Group</TableHead>
            <TableHead className={`${thClass} text-right`}>Bets</TableHead>
            <TableHead className={`${thClass} text-right`}>Win Rate</TableHead>
            <TableHead className={`${thClass} text-right`}>Mean CLV</TableHead>
            <TableHead className={`${thClass} text-right`}>Net P&L</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {MOCK_DATA.bySignal.map((row) => (
            <TableRow key={row.signal} className="border-[#262626] hover:bg-[#1a1a1a]">
              <TableCell className="py-3 text-sm text-gray-300 pl-0">{row.signal}</TableCell>
              <TableCell className={`${tdBase} text-right text-gray-400`}>{row.bets}</TableCell>
              <TableCell className={`${tdBase} text-right ${winRateColor(row.winRate)}`}>{fmtPct(row.winRate)}</TableCell>
              <TableCell className={`${tdBase} text-right ${clvColor(row.meanCLV)}`}>{row.meanCLV >= 0 ? "+" : ""}{fmtPct(row.meanCLV)}</TableCell>
              <TableCell className={`${tdBase} text-right ${pnlColor(row.netPnl)}`}>{fmtPnl(row.netPnl)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function BreakdownTabs() {
  return (
    <div className="rounded-xl border border-[#262626] bg-[#141414] px-5 py-5">
      <Tabs defaultValue="conviction">
        <TabsList className="bg-[#0a0a0a] border border-[#262626] mb-5">
          <TabsTrigger value="market" className="text-xs data-[state=active]:bg-[#141414] data-[state=active]:text-white">
            By Market
          </TabsTrigger>
          <TabsTrigger value="conviction" className="text-xs data-[state=active]:bg-[#141414] data-[state=active]:text-white">
            By Conviction
          </TabsTrigger>
          <TabsTrigger value="signal" className="text-xs data-[state=active]:bg-[#141414] data-[state=active]:text-white">
            By Signal
          </TabsTrigger>
        </TabsList>
        <TabsContent value="market">
          <ByMarketTable />
        </TabsContent>
        <TabsContent value="conviction">
          <ByConvictionTable />
        </TabsContent>
        <TabsContent value="signal">
          <BySignalTable />
        </TabsContent>
      </Tabs>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Recent results
// ---------------------------------------------------------------------------

function RecentResults() {
  const results = MOCK_DATA.recentResults
  return (
    <div>
      <h2 className="mb-4 text-base font-semibold text-white">Recent Results</h2>
      <div className="overflow-x-auto rounded-xl border border-[#262626] bg-[#141414]">
        <Table>
          <TableHeader>
            <TableRow className="border-[#262626] hover:bg-transparent">
              <TableHead className={`${thClass} pl-5`}>Date</TableHead>
              <TableHead className={thClass}>Game</TableHead>
              <TableHead className={thClass}>Market</TableHead>
              <TableHead className={thClass}>Side</TableHead>
              <TableHead className={`${thClass} text-right`}>Model%</TableHead>
              <TableHead className={`${thClass} text-right`}>Bovada%</TableHead>
              <TableHead className={`${thClass} text-right`}>Edge</TableHead>
              <TableHead className={thClass}>Result</TableHead>
              <TableHead className={`${thClass} text-right pr-5`}>CLV</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {results.map((r, i) => (
              <TableRow key={i} className="border-[#262626] hover:bg-[#1a1a1a]">
                <TableCell className="py-3 pl-5 text-xs text-gray-500 whitespace-nowrap">{r.date}</TableCell>
                <TableCell className="py-3 text-sm text-gray-300 whitespace-nowrap font-medium">{r.game}</TableCell>
                <TableCell className="py-3 text-xs text-gray-400 whitespace-nowrap">{r.market}</TableCell>
                <TableCell className="py-3 text-xs text-gray-400 whitespace-nowrap">{r.side}</TableCell>
                <TableCell className="py-3 text-right font-mono text-sm text-[#10b981] whitespace-nowrap">{fmtPct(r.modelProb)}</TableCell>
                <TableCell className="py-3 text-right font-mono text-sm text-gray-400 whitespace-nowrap">{fmtPct(r.bovadaProb)}</TableCell>
                <TableCell className="py-3 text-right font-mono text-sm text-gray-300 whitespace-nowrap">
                  {r.edge >= 0 ? "+" : ""}{fmtPct(r.edge)}
                </TableCell>
                <TableCell className="py-3">
                  <ResultBadge result={r.result} />
                </TableCell>
                <TableCell className={`py-3 pr-5 text-right font-mono text-sm whitespace-nowrap ${clvColor(r.clv)}`}>
                  {r.clv >= 0 ? "+" : ""}{fmtPct(r.clv)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function PerformancePage() {
  const [sizing, setSizing] = useState<SizingMethod>("Flat")
  const sizingOptions: SizingMethod[] = ["Flat", "Kelly", "Portfolio Kelly"]

  return (
    <div className="min-h-screen bg-[#0a0a0a] font-sans">
      <Navbar />
      <main className="mx-auto max-w-6xl px-4 pb-20">
        {/* Page header */}
        <div className="flex flex-col gap-4 pt-10 pb-6 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-white md:text-4xl">
              Performance
            </h1>
            <p className="mt-2 text-sm text-gray-400">
              Season record from first qualified pick through today.
            </p>
          </div>
          {/* Sizing toggle */}
          <div className="flex shrink-0 rounded-lg border border-[#262626] bg-[#141414] p-1">
            {sizingOptions.map((opt) => (
              <button
                key={opt}
                onClick={() => setSizing(opt)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  sizing === opt
                    ? "bg-[#10b981] text-[#0a0a0a]"
                    : "text-gray-500 hover:text-gray-300"
                }`}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>

        {/* Stat tiles */}
        <StatTiles sizing={sizing} />

        {/* P&L curve */}
        <div className="mt-5">
          <PLCurve sizing={sizing} />
        </div>

        {/* Breakdown tabs */}
        <div className="mt-5">
          <BreakdownTabs />
        </div>

        {/* Recent results */}
        <div className="mt-8">
          <RecentResults />
        </div>
      </main>
    </div>
  )
}
