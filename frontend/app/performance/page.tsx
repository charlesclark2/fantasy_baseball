"use client"

import { useMemo, useState } from "react"
import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { AuthGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { Nav } from "@/components/nav"
import { apiFetch } from "@/lib/api"
// E9.26 — canonical win-rate formatting + color shared across surfaces.
import { fmtPct, winRateColor, recordFromOutcomes, SMALL_SAMPLE_N } from "@/lib/metrics"
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  Cell,
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

// ---------------------------------------------------------------------------
// Bankroll growth types (E9.17)
// ---------------------------------------------------------------------------

interface BankrollGrowth {
  total_deposited: number
  total_withdrawn: number
  net_deposits: number
  current_balance: number
  betting_pnl: number
  growth_pct: number | null
}

interface BankrollData {
  overall_growth: BankrollGrowth
  per_book_growth: Record<string, BankrollGrowth & { baseline_reset_at?: string | null }>
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MarketMetrics {
  season: number
  market_type: string
  n_predictions: number
  brier_score: number | null
  avg_clv: number | null
  clv_positive_pct: number | null
  win_rate: number | null
}

interface ModelMetricsResponse {
  season: number | null
  markets: MarketMetrics[]
}

interface PerformanceBet {
  bet_id: string
  game_pk: number
  score_date: string
  matchup: string | null
  market: string
  bookmaker: string | null
  american_odds: number | null
  stake: number
  outcome: string | null
  profit_loss: number | null
  ev: number | null
  model_prob: number | null
  placed_at: string
}

interface PerformanceBetsResponse {
  season: number | null
  bets: PerformanceBet[]
  total: number
  settled_count: number
  net_pnl: number | null
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtSignedPct(val: number | null | undefined) {
  if (val == null) return "—"
  return `${val >= 0 ? "+" : ""}${(val * 100).toFixed(1)}%`
}

function fmtPnl(val: number | null | undefined) {
  if (val == null) return "—"
  const rounded = Math.round(val)
  return rounded >= 0 ? `+$${rounded}` : `-$${Math.abs(rounded)}`
}

function fmtPnlExact(val: number | null | undefined) {
  if (val == null) return "—"
  const abs = Math.abs(val).toFixed(2)
  return val >= 0 ? `+$${abs}` : `-$${abs}`
}

function fmtOdds(val: number | null | undefined) {
  if (val == null) return "—"
  return val > 0 ? `+${val}` : `${val}`
}

function clvColor(val: number | null | undefined) {
  return (val ?? 0) >= 0 ? "text-[#10b981]" : "text-[#ef4444]"
}

function pnlColor(val: number | null | undefined) {
  return (val ?? 0) >= 0 ? "text-[#10b981]" : "text-[#ef4444]"
}

// ---------------------------------------------------------------------------
// Info tooltip — white bg, black text, appears above on hover
// ---------------------------------------------------------------------------

function InfoTooltip({ text }: { text: string }) {
  return (
    <span className="group relative inline-block">
      <span className="ml-1 cursor-help select-none text-gray-600 text-xs hover:text-gray-400">ⓘ</span>
      <span className="pointer-events-none invisible group-hover:visible absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 rounded-md bg-white px-3 py-2 text-xs text-black shadow-xl leading-relaxed">
        {text}
        <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-white" />
      </span>
    </span>
  )
}

// ---------------------------------------------------------------------------
// Result badge — outcome is "win" / "loss" / "push" (strings from settle op)
// ---------------------------------------------------------------------------

function ResultBadge({ outcome }: { outcome: string | null }) {
  if (outcome === "win") {
    return (
      <Badge className="bg-[#10b981]/15 text-[#10b981] border border-[#10b981]/30 text-xs font-semibold">
        Win
      </Badge>
    )
  }
  if (outcome === "loss") {
    return (
      <Badge className="bg-[#ef4444]/15 text-[#ef4444] border border-[#ef4444]/30 text-xs font-semibold">
        Loss
      </Badge>
    )
  }
  if (outcome === "push") {
    return (
      <Badge variant="outline" className="border-gray-600 text-gray-500 text-xs font-semibold">
        Push
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="border-[#f59e0b]/30 text-[#f59e0b] text-xs font-semibold">
      Pending
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

function BrierTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-[#262626] bg-[#141414] px-3 py-2 shadow-xl">
      <p className="text-xs text-gray-400 mb-1">{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey ?? p.name} className="text-sm font-semibold font-mono text-gray-200">
          {p.name}: <span className="text-white">{p.value?.toFixed(3)}</span>
        </p>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Season selector
// ---------------------------------------------------------------------------

type Season = number | null

const SEASON_OPTIONS: { label: string; value: Season }[] = [
  { label: "2026", value: 2026 },
  { label: "2025", value: 2025 },
  { label: "2024", value: 2024 },
  { label: "2023", value: 2023 },
  { label: "All", value: null },
]

function SeasonSelector({
  season,
  onChange,
}: {
  season: Season
  onChange: (s: Season) => void
}) {
  return (
    <div className="flex shrink-0 rounded-lg border border-[#262626] bg-[#141414] p-1">
      {SEASON_OPTIONS.map((opt) => (
        <button
          key={String(opt.value)}
          onClick={() => onChange(opt.value)}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            season === opt.value
              ? "bg-[#10b981] text-[#0a0a0a]"
              : "text-gray-500 hover:text-gray-300"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Summary tiles — driven by /performance/bets per-user data
// ---------------------------------------------------------------------------

interface BetSummary {
  wins: number
  losses: number
  pushes: number
  settled: number
  winRate: number | null
  lowSample: boolean
  decisive: number
  netPnl: number | null
  totalStake: number
  roi: number | null
  total: number
}

function deriveSummary(data: PerformanceBetsResponse | undefined): BetSummary {
  const bets = data?.bets ?? []
  // E9.26 — canonical: win rate excludes pushes; ROI is realized settlement (net
  // of vig) over settled stake — `bets` are the settled bets the backend returns.
  const record = recordFromOutcomes(bets.map(b => b.outcome))
  const settled = data?.settled_count ?? 0
  const netPnl = data?.net_pnl ?? null
  const totalStake = bets.reduce((s, b) => s + (b.stake ?? 0), 0)
  const roi = totalStake > 0 && netPnl != null ? netPnl / totalStake : null
  return {
    wins: record.wins, losses: record.losses, pushes: record.pushes,
    settled, winRate: record.winRate, lowSample: record.lowSample, decisive: record.decisive,
    netPnl, totalStake, roi, total: data?.total ?? 0,
  }
}

function StatTiles({
  summary,
  bankrollGrowth,
}: {
  summary: BetSummary
  bankrollGrowth: BankrollGrowth | null
}) {
  const tiles = [
    {
      label: "Settled Bets",
      value: summary.settled.toString(),
      sub: `${summary.wins}W · ${summary.losses}L · ${summary.pushes}P`,
      valueClass: "text-white",
      tooltip: undefined as string | undefined,
    },
    {
      label: "Win Rate",
      value: fmtPct(summary.winRate),
      sub: summary.lowSample && summary.decisive > 0
        ? `excl. pushes · small sample (${summary.decisive} of ${SMALL_SAMPLE_N})`
        : "excl. pushes",
      valueClass: winRateColor(summary.winRate),
      tooltip: undefined,
    },
    {
      label: "Net P&L",
      value: fmtPnlExact(summary.netPnl),
      sub: summary.roi != null ? `${fmtSignedPct(summary.roi)} ROI` : undefined,
      valueClass: pnlColor(summary.netPnl),
      tooltip: undefined,
    },
    {
      label: "Total Staked",
      value: `$${summary.totalStake.toFixed(0)}`,
      sub: `${summary.total} total bets`,
      valueClass: "text-gray-300",
      tooltip: undefined,
    },
  ]

  const showGrowth = bankrollGrowth != null && bankrollGrowth.total_deposited > 0
  const growthPct = showGrowth && bankrollGrowth.growth_pct != null
    ? `${bankrollGrowth.growth_pct >= 0 ? "+" : ""}${(bankrollGrowth.growth_pct * 100).toFixed(1)}%`
    : null
  const growthPnlStr = showGrowth
    ? (bankrollGrowth.betting_pnl >= 0
        ? `+$${bankrollGrowth.betting_pnl.toFixed(2)}`
        : `-$${Math.abs(bankrollGrowth.betting_pnl).toFixed(2)}`)
    : null

  return (
    <div className={`grid grid-cols-2 gap-3 ${showGrowth ? "lg:grid-cols-5" : "lg:grid-cols-4"}`}>
      {tiles.map((tile) => (
        <div
          key={tile.label}
          className="flex flex-col justify-between rounded-xl border border-[#262626] bg-[#141414] px-5 py-4"
        >
          <p className="text-xs uppercase tracking-wider text-gray-500 font-medium leading-relaxed">
            {tile.label}
          </p>
          <p className={`mt-2 text-3xl font-bold tracking-tight font-mono ${tile.valueClass}`}>
            {tile.value}
          </p>
          {tile.sub && (
            <p className="mt-1 text-xs text-gray-500">{tile.sub}</p>
          )}
        </div>
      ))}

      {/* Bankroll growth tile — only shown when deposits are tracked */}
      {showGrowth && (
        <div className="flex flex-col justify-between rounded-xl border border-[#262626] bg-[#141414] px-5 py-4">
          <p className="text-xs text-gray-500 font-medium leading-relaxed flex items-center gap-1">
            Bankroll Growth
            <InfoTooltip text="Growth % = betting P&L ÷ total deposited. Deposits and withdrawals are netted out so the figure reflects only betting results, not cash movement. Distinct from ROI (return on stake/turnover)." />
          </p>
          <p className={`mt-2 text-3xl font-bold tracking-tight font-mono ${pnlColor(bankrollGrowth.growth_pct)}`}>
            {growthPct ?? "—"}
          </p>
          <p className="mt-1 text-xs text-gray-500">
            {growthPnlStr}{" "}betting P&amp;L
          </p>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Per-book bankroll breakdown — read-only, from /users/bankroll per_book_growth
// ---------------------------------------------------------------------------

type PerBookGrowth = BankrollGrowth & { baseline_reset_at?: string | null }

function PerBookBreakdown({ perBook }: { perBook: Record<string, PerBookGrowth> }) {
  const rows = useMemo(
    () =>
      Object.entries(perBook)
        .filter(([, g]) => g.total_deposited > 0)
        .map(([book, g]) => ({ book, ...g }))
        .sort((a, b) => b.current_balance - a.current_balance),
    [perBook]
  )

  // Hide until at least one book has a deposit recorded.
  if (rows.length === 0) return null

  return (
    <div className="rounded-xl border border-[#262626] bg-[#141414] px-5 py-5">
      <div className="flex items-center gap-1.5 mb-1">
        <h2 className="text-sm font-semibold text-white">Bankroll by Sportsbook</h2>
        <InfoTooltip text="Your tracked balance per book. Betting P&L = balance − net deposits; Growth % = betting P&L ÷ total deposited (cash flows netted out). Distinct from ROI (return on stake). Self-reported from Settings → Sportsbooks." />
      </div>
      <p className="text-xs text-gray-500 mb-4">
        Growth is return on deposited bankroll — netting out deposits and withdrawals. Distinct from ROI (return on stake).
      </p>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="border-[#262626] hover:bg-transparent">
              <TableHead className={`${thClass} pl-0`}>Book</TableHead>
              <TableHead className={`${thClass} text-right`}>Balance</TableHead>
              <TableHead className={`${thClass} text-right`}>Net Deposits</TableHead>
              <TableHead className={`${thClass} text-right`}>Betting P&L</TableHead>
              <TableHead className={`${thClass} text-right`}>Growth</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.book} className="border-[#262626] hover:bg-[#1a1a1a]">
                <TableCell className="py-3 text-sm text-gray-300 pl-0">
                  {r.book}
                  {r.baseline_reset_at && (
                    <span className="ml-2 text-[10px] text-gray-600">· rebased</span>
                  )}
                </TableCell>
                <TableCell className={`${tdBase} text-right text-gray-300`}>
                  ${r.current_balance.toFixed(2)}
                </TableCell>
                <TableCell className={`${tdBase} text-right text-gray-400`}>
                  ${r.net_deposits.toFixed(2)}
                </TableCell>
                <TableCell className={`${tdBase} text-right ${pnlColor(r.betting_pnl)}`}>
                  {fmtPnlExact(r.betting_pnl)}
                </TableCell>
                <TableCell className={`${tdBase} text-right ${pnlColor(r.growth_pct)}`}>
                  {fmtSignedPct(r.growth_pct)}
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
// Model skill strip — driven by /performance/model (global, all picks)
// ---------------------------------------------------------------------------

const TOOLTIP_BRIER =
  "Brier Score measures calibration — how close model probabilities are to actual outcomes. Lower is better. A perfect model = 0; random guessing ≈ 0.25."
const TOOLTIP_CLV =
  "Closing Line Value (CLV): the move between the price when the model predicted and the market's closing price, measured in the direction of the model's pick. Near zero means no systematic timing difference versus the market."
const TOOLTIP_CLVPCT =
  "% of picks whose side gained closing-line value (CLV > 0), measured in the model's pick direction. Around 50% means no consistent timing advantage over the market."
const TOOLTIP_WINRATE =
  "% of the model's directional picks that won — the side the model favored (home or away for Moneyline, Over or Under for Totals), one pick per game. Excludes pushes."
const TOOLTIP_TOTALS =
  "Totals and Moneyline are each scored as one pick per game — the side the model favored — so the two counts are similar."

function MarketCard({ m }: { m: MarketMetrics }) {
  const isTotals = m.market_type !== "h2h"
  return (
    <div className="rounded-lg border border-[#1f1f1f] bg-[#0f0f0f] px-4 py-3">
      <div className="flex items-center gap-1 mb-3">
        <p className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
          {isTotals ? "Totals (Over / Under)" : "Moneyline (H2H)"}
        </p>
        {isTotals && <InfoTooltip text={TOOLTIP_TOTALS} />}
      </div>
      <div className="grid grid-cols-5 gap-2 text-center">
        <div>
          <p className="text-xs text-gray-500">Picks</p>
          <p className="mt-0.5 font-mono text-sm text-white">
            {m.n_predictions.toLocaleString()}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500 flex items-center justify-center">
            Brier<InfoTooltip text={TOOLTIP_BRIER} />
          </p>
          <p className="mt-0.5 font-mono text-sm text-gray-300">
            {m.brier_score?.toFixed(3) ?? "—"}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500 flex items-center justify-center">
            Avg CLV<InfoTooltip text={TOOLTIP_CLV} />
          </p>
          <p className={`mt-0.5 font-mono text-sm ${clvColor(m.avg_clv)}`}>
            {fmtSignedPct(m.avg_clv)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500 flex items-center justify-center">
            CLV+%<InfoTooltip text={TOOLTIP_CLVPCT} />
          </p>
          <p className={`mt-0.5 font-mono text-sm ${(m.clv_positive_pct ?? 0) >= 0.5 ? "text-[#10b981]" : "text-gray-300"}`}>
            {fmtPct(m.clv_positive_pct)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500 flex items-center justify-center">
            Win %<InfoTooltip text={TOOLTIP_WINRATE} />
          </p>
          <p className={`mt-0.5 font-mono text-sm ${winRateColor(m.win_rate)}`}>
            {fmtPct(m.win_rate)}
          </p>
        </div>
      </div>
    </div>
  )
}

function AllSeasonsGrid({ markets }: { markets: MarketMetrics[] }) {
  const byYear = new Map<number, MarketMetrics[]>()
  for (const m of markets) {
    if (!byYear.has(m.season)) byYear.set(m.season, [])
    byYear.get(m.season)!.push(m)
  }
  const years = Array.from(byYear.keys()).sort((a, b) => b - a)

  return (
    <div className="space-y-4">
      {years.map((year) => (
        <div key={year}>
          <p className="text-xs font-mono text-gray-300 font-semibold mb-2">{year}</p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {(byYear.get(year) ?? []).map((m) => (
              <div
                key={m.market_type}
                className="rounded-lg border border-[#1f1f1f] bg-[#0f0f0f] px-3 py-2.5"
              >
                <p className="text-xs font-semibold text-gray-400 mb-2.5">
                  {m.market_type === "h2h" ? "Moneyline" : "Totals"}
                </p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                  <div>
                    <p className="text-xs text-gray-600">Picks</p>
                    <p className="font-mono text-sm text-gray-300 mt-0.5">
                      {m.n_predictions.toLocaleString()}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-600 flex items-center gap-0.5">
                      Brier<InfoTooltip text={TOOLTIP_BRIER} />
                    </p>
                    <p className="font-mono text-sm text-gray-300 mt-0.5">
                      {m.brier_score?.toFixed(3) ?? "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-600 flex items-center gap-0.5">
                      Avg CLV<InfoTooltip text={TOOLTIP_CLV} />
                    </p>
                    <p className={`font-mono text-sm mt-0.5 ${clvColor(m.avg_clv)}`}>
                      {fmtSignedPct(m.avg_clv)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-600 flex items-center gap-0.5">
                      Win %<InfoTooltip text={TOOLTIP_WINRATE} />
                    </p>
                    <p className={`font-mono text-sm mt-0.5 ${winRateColor(m.win_rate)}`}>
                      {fmtPct(m.win_rate)}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

const BRIER_Y_DOMAIN: [number, number] = [0.17, 0.27]

function BrierChart({ markets, season }: { markets: MarketMetrics[]; season: Season }) {
  const valid = markets.filter((m) => m.brier_score != null)
  if (valid.length === 0) return null

  if (season === null) {
    // All seasons: grouped vertical bar chart — one group per year, H2H + Totals bars
    const byYear = new Map<number, { h2h?: number; totals?: number }>()
    for (const m of valid) {
      if (!byYear.has(m.season)) byYear.set(m.season, {})
      const entry = byYear.get(m.season)!
      if (m.market_type === "h2h") entry.h2h = m.brier_score!
      else entry.totals = m.brier_score!
    }
    const data = Array.from(byYear.entries())
      .sort(([a], [b]) => a - b)
      .map(([year, vals]) => ({ year: String(year), Moneyline: vals.h2h, Totals: vals.totals }))

    return (
      <div className="mt-6 pt-5 border-t border-[#1f1f1f]">
        <div className="flex items-center gap-1 mb-4">
          <p className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
            Brier Score by Season
          </p>
          <InfoTooltip text="Brier Score measures probability calibration. Lower is better — a perfect model = 0.0, random guessing ≈ 0.25. The dashed red line marks the random baseline." />
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data} barCategoryGap="35%" barGap={3} margin={{ top: 4, right: 24, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#262626" vertical={false} />
            <XAxis dataKey="year" tick={{ fill: "#6b7280", fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis
              domain={BRIER_Y_DOMAIN}
              tick={{ fill: "#6b7280", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => v.toFixed(2)}
              width={40}
            />
            <Tooltip content={<BrierTooltip />} />
            <ReferenceLine
              y={0.25}
              stroke="#ef4444"
              strokeDasharray="4 3"
              label={{ value: "random", position: "insideTopRight", fill: "#ef4444", fontSize: 10 }}
            />
            <Bar dataKey="Moneyline" fill="#10b981" radius={[3, 3, 0, 0]} maxBarSize={28} />
            <Bar dataKey="Totals" fill="#f59e0b" radius={[3, 3, 0, 0]} maxBarSize={28} />
          </BarChart>
        </ResponsiveContainer>
        <div className="flex items-center gap-5 mt-2 justify-center">
          <span className="flex items-center gap-1.5 text-xs text-gray-500">
            <span className="inline-block w-2.5 h-2.5 rounded-sm bg-[#10b981]" />
            Moneyline
          </span>
          <span className="flex items-center gap-1.5 text-xs text-gray-500">
            <span className="inline-block w-2.5 h-2.5 rounded-sm bg-[#f59e0b]" />
            Totals
          </span>
          <span className="flex items-center gap-1.5 text-xs text-gray-500">
            <span className="inline-block w-7 border-t border-dashed border-[#ef4444]" />
            Random
          </span>
        </div>
        <p className="text-xs text-gray-600 mt-3">
          * 2026 is our first live prediction season. Prior seasons reflect model development and backtesting — those Brier scores are in-sample estimates, not forward predictions.
        </p>
      </div>
    )
  }

  // Single season: horizontal bar chart — two rows (Moneyline / Totals), X = Brier score
  const data = valid.map((m) => ({
    market: m.market_type === "h2h" ? "Moneyline" : "Totals",
    brier: m.brier_score!,
    color: m.market_type === "h2h" ? "#10b981" : "#f59e0b",
  }))

  return (
    <div className="mt-6 pt-5 border-t border-[#1f1f1f]">
      <div className="flex items-center gap-1 mb-4">
        <p className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
          Brier Score — {season}
        </p>
        <InfoTooltip text="Brier Score measures probability calibration. Lower is better — a perfect model = 0.0, random guessing ≈ 0.25. The dashed red line marks the random baseline." />
      </div>
      <ResponsiveContainer width="100%" height={120}>
        <BarChart
          layout="vertical"
          data={data}
          barCategoryGap="40%"
          margin={{ top: 4, right: 48, left: 0, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#262626" horizontal={false} />
          <XAxis
            type="number"
            domain={BRIER_Y_DOMAIN}
            tick={{ fill: "#6b7280", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) => v.toFixed(2)}
          />
          <YAxis
            type="category"
            dataKey="market"
            tick={{ fill: "#9ca3af", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={72}
          />
          <Tooltip content={<BrierTooltip />} />
          <ReferenceLine
            x={0.25}
            stroke="#ef4444"
            strokeDasharray="4 3"
            label={{ value: "random", position: "top", fill: "#ef4444", fontSize: 10 }}
          />
          <Bar dataKey="brier" name="Brier" radius={[0, 3, 3, 0]} maxBarSize={24}>
            {data.map((entry, i) => (
              <Cell key={i} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function ModelSkillStrip({
  data,
  season,
  includeDegraded,
  onToggleDegraded,
}: {
  data: ModelMetricsResponse | undefined
  season: Season
  includeDegraded: boolean
  onToggleDegraded: () => void
}) {
  const markets = data?.markets ?? []
  const isAllSeasons = season === null
  return (
    <div className="rounded-xl border border-[#262626] bg-[#141414] px-5 py-4">
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs uppercase tracking-wider text-gray-500 font-medium">
          {isAllSeasons ? "Model Skill — All Seasons" : "Model Skill — All Picks"}
        </p>
        <button
          onClick={onToggleDegraded}
          className={`text-xs px-2.5 py-1 rounded border transition-colors ${
            includeDegraded
              ? "border-[#f59e0b]/40 text-[#f59e0b] bg-[#f59e0b]/10 hover:bg-[#f59e0b]/20"
              : "border-[#262626] text-gray-600 hover:text-gray-400 hover:border-gray-600"
          }`}
          title={includeDegraded ? "Degraded predictions included — click to exclude" : "Degraded predictions excluded — click to include"}
        >
          {includeDegraded ? "incl. degraded" : "excl. degraded"}
        </button>
      </div>
      {markets.length === 0 ? (
        <p className="text-sm text-gray-500">No model data available.</p>
      ) : isAllSeasons ? (
        <>
          <AllSeasonsGrid markets={markets} />
          <BrierChart markets={markets} season={null} />
        </>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            {markets.map((m) => (
              <MarketCard key={`${m.season}-${m.market_type}`} m={m} />
            ))}
          </div>
          <BrierChart markets={markets} season={season} />
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// P&L curve — real $ from /performance/bets profit_loss, with market filter
// ---------------------------------------------------------------------------

type MarketFilter = "all" | "h2h" | "totals"

const MARKET_FILTER_LABELS: Record<MarketFilter, string> = {
  all: "All",
  h2h: "H2H",
  totals: "Totals",
}

function PLCurve({ bets }: { bets: PerformanceBet[] }) {
  const [filter, setFilter] = useState<MarketFilter>("all")

  const data = useMemo(() => {
    const filtered = filter === "all" ? bets : bets.filter(b => marketKey(b.market) === filter)
    const settled = filtered
      .filter(b => b.outcome != null && b.profit_loss != null)
      .sort((a, b) => a.score_date.localeCompare(b.score_date))
    let running = 0
    return settled.map(b => {
      running += b.profit_loss!
      return { date: b.score_date, pnl: Math.round(running * 100) / 100 }
    })
  }, [bets, filter])

  return (
    <div className="rounded-xl border border-[#262626] bg-[#141414] px-5 pt-5 pb-4">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex items-center gap-1.5 min-w-0">
          <h2 className="text-sm font-semibold text-white whitespace-nowrap">
            Cumulative P&amp;L — Flat Stake
          </h2>
          <InfoTooltip text="Running total of profit/loss over time, assuming the same flat stake on every bet. The green line is cumulative dollars gained or lost. Use the filters to see how H2H vs. Totals bets each contribute." />
        </div>
        <div className="flex shrink-0 rounded-md border border-[#262626] bg-[#0a0a0a] p-0.5">
          {(Object.keys(MARKET_FILTER_LABELS) as MarketFilter[]).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                filter === f
                  ? "bg-[#10b981] text-[#0a0a0a]"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              {MARKET_FILTER_LABELS[f]}
            </button>
          ))}
        </div>
      </div>
      {data.length === 0 ? (
        <div className="flex h-[240px] items-center justify-center text-sm text-gray-500">
          No settled bets yet.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#262626" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fill: "#6b7280", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              dy={6}
              minTickGap={24}
            />
            <YAxis
              tick={{ fill: "#6b7280", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => `$${v}`}
              width={52}
            />
            <Tooltip content={<ChartTooltip />} />
            <ReferenceLine y={0} stroke="#374151" strokeDasharray="4 3" />
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
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// By-market breakdown — computed client-side from bets list
// ---------------------------------------------------------------------------

interface MarketAgg {
  market_type: string
  total: number
  wins: number
  losses: number
  pushes: number
  win_rate: number | null
  net_pnl: number
}

function marketKey(market: string): string {
  if (market.startsWith("h2h")) return "h2h"
  if (market === "over" || market === "under") return "totals"
  return market
}

function computeByMarket(bets: PerformanceBet[]): MarketAgg[] {
  const map = new Map<string, MarketAgg>()
  for (const b of bets) {
    if (b.outcome == null) continue
    const key = marketKey(b.market)
    if (!map.has(key)) {
      map.set(key, { market_type: key, total: 0, wins: 0, losses: 0, pushes: 0, win_rate: null, net_pnl: 0 })
    }
    const agg = map.get(key)!
    agg.total++
    if (b.outcome === "win") agg.wins++
    else if (b.outcome === "loss") agg.losses++
    else agg.pushes++
    agg.net_pnl += b.profit_loss ?? 0
  }
  for (const agg of map.values()) {
    const decisive = agg.wins + agg.losses
    agg.win_rate = decisive > 0 ? agg.wins / decisive : null
  }
  return Array.from(map.values()).sort((a, b) => a.market_type.localeCompare(b.market_type))
}

const thClass = "text-xs uppercase tracking-wider text-gray-500 font-medium"
const tdBase = "py-3 font-mono text-sm"

function ByMarketTable({ bets }: { bets: PerformanceBet[] }) {
  const rows = useMemo(() => computeByMarket(bets), [bets])
  if (rows.length === 0) {
    return (
      <div className="text-sm text-gray-500 py-8 text-center">
        No settled bets yet.
      </div>
    )
  }
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="border-[#262626] hover:bg-transparent">
            <TableHead className={`${thClass} pl-0`}>Market</TableHead>
            <TableHead className={`${thClass} text-right`}>Bets</TableHead>
            <TableHead className={`${thClass} text-right`}>Record</TableHead>
            <TableHead className={`${thClass} text-right`}>Win Rate</TableHead>
            <TableHead className={`${thClass} text-right`}>Net P&L</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.market_type} className="border-[#262626] hover:bg-[#1a1a1a]">
              <TableCell className="py-3 text-sm text-gray-300 pl-0">{r.market_type}</TableCell>
              <TableCell className={`${tdBase} text-right text-gray-400`}>{r.total}</TableCell>
              <TableCell className={`${tdBase} text-right text-gray-400`}>
                {r.wins}W–{r.losses}L{r.pushes > 0 ? `–${r.pushes}P` : ""}
              </TableCell>
              <TableCell className={`${tdBase} text-right ${winRateColor(r.win_rate)}`}>
                {fmtPct(r.win_rate)}
              </TableCell>
              <TableCell className={`${tdBase} text-right ${pnlColor(r.net_pnl)}`}>
                {fmtPnlExact(r.net_pnl)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function BreakdownTabs({ bets }: { bets: PerformanceBet[] }) {
  return (
    <div className="rounded-xl border border-[#262626] bg-[#141414] px-5 py-5">
      <Tabs defaultValue="market">
        <TabsList className="bg-[#0a0a0a] border border-[#262626] mb-5">
          <TabsTrigger
            value="market"
            className="text-xs data-[state=active]:bg-[#141414] data-[state=active]:text-white"
          >
            By Market
          </TabsTrigger>
          <TabsTrigger
            value="conviction"
            className="text-xs data-[state=active]:bg-[#141414] data-[state=active]:text-white"
          >
            By Conviction
          </TabsTrigger>
          <TabsTrigger
            value="signal"
            className="text-xs data-[state=active]:bg-[#141414] data-[state=active]:text-white"
          >
            By Signal
          </TabsTrigger>
        </TabsList>
        <TabsContent value="market">
          <ByMarketTable bets={bets} />
        </TabsContent>
        <TabsContent value="conviction">
          <div className="text-sm text-gray-500 py-8 text-center">
            Per-conviction breakdowns coming in a future release.
          </div>
        </TabsContent>
        <TabsContent value="signal">
          <div className="text-sm text-gray-500 py-8 text-center">
            Per-signal breakdowns coming in a future release.
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Bet log — all bets newest-first, paginated 25/page
// ---------------------------------------------------------------------------

const BET_LOG_PAGE_SIZE = 25

function BetLogTable({ bets }: { bets: PerformanceBet[] }) {
  const sorted = useMemo(
    () => [...bets].sort((a, b) => b.score_date.localeCompare(a.score_date)),
    [bets]
  )

  const [page, setPage] = useState(0)
  const totalPages = Math.max(1, Math.ceil(sorted.length / BET_LOG_PAGE_SIZE))
  const pageBets = sorted.slice(page * BET_LOG_PAGE_SIZE, (page + 1) * BET_LOG_PAGE_SIZE)

  // Reset to first page when bets list changes (season switch)
  useMemo(() => { setPage(0) }, [sorted])

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold text-white">Bet Log</h2>
          <InfoTooltip text="Model Prob is the probability our model assigned at bet time. EV is the expected value edge over the offered odds. These show what signals we were reading when the pick was made." />
        </div>
        {sorted.length > BET_LOG_PAGE_SIZE && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 font-mono">
              {page + 1} / {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="rounded border border-[#262626] px-2.5 py-1 text-xs text-gray-400 hover:text-white hover:border-gray-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              Prev
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="rounded border border-[#262626] px-2.5 py-1 text-xs text-gray-400 hover:text-white hover:border-gray-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              Next
            </button>
          </div>
        )}
      </div>
      <div className="overflow-x-auto rounded-xl border border-[#262626] bg-[#141414]">
        {sorted.length === 0 ? (
          <div className="py-8 text-center text-sm text-gray-500">
            No settled bets yet.
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="border-[#262626] hover:bg-transparent">
                <TableHead className={`${thClass} pl-5`}>Date</TableHead>
                <TableHead className={thClass}>Game</TableHead>
                <TableHead className={`${thClass} hidden sm:table-cell`}>Market</TableHead>
                <TableHead className={`${thClass} hidden sm:table-cell`}>Book</TableHead>
                <TableHead className={`${thClass} text-right hidden sm:table-cell`}>Odds</TableHead>
                <TableHead className={`${thClass} text-right hidden sm:table-cell`}>Stake</TableHead>
                <TableHead className={`${thClass} text-right hidden md:table-cell`}>Model</TableHead>
                <TableHead className={thClass}>Result</TableHead>
                <TableHead className={`${thClass} text-right pr-5`}>P&L</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pageBets.map((b) => (
                <TableRow key={b.bet_id} className="border-[#262626] hover:bg-[#1a1a1a]">
                  <TableCell className="py-3 pl-5 text-xs text-gray-500 whitespace-nowrap">
                    {b.score_date}
                  </TableCell>
                  <TableCell className="py-3 text-sm text-gray-300 whitespace-nowrap font-medium">
                    {b.matchup ?? `Game ${b.game_pk}`}
                    <div className="sm:hidden text-xs text-gray-500 font-normal mt-0.5">{b.market}</div>
                  </TableCell>
                  <TableCell className="py-3 text-xs text-gray-400 whitespace-nowrap hidden sm:table-cell">
                    {b.market}
                  </TableCell>
                  <TableCell className="py-3 text-xs text-gray-500 whitespace-nowrap hidden sm:table-cell">
                    {b.bookmaker ?? "—"}
                  </TableCell>
                  <TableCell className="py-3 text-right font-mono text-sm text-gray-300 whitespace-nowrap hidden sm:table-cell">
                    {fmtOdds(b.american_odds)}
                  </TableCell>
                  <TableCell className="py-3 text-right font-mono text-sm text-gray-400 whitespace-nowrap hidden sm:table-cell">
                    ${b.stake.toFixed(0)}
                  </TableCell>
                  <TableCell className="py-3 text-right whitespace-nowrap hidden md:table-cell">
                    {b.model_prob != null ? (
                      <span className="font-mono text-sm text-gray-300">
                        {fmtPct(b.model_prob)}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-600">—</span>
                    )}
                    {b.ev != null && (
                      <span className={`ml-1.5 font-mono text-xs ${clvColor(b.ev)}`}>
                        {fmtSignedPct(b.ev)}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="py-3">
                    <ResultBadge outcome={b.outcome} />
                    {/* Model context shown on mobile when Model column is hidden */}
                    {b.model_prob != null && (
                      <div className="md:hidden mt-1 flex items-center gap-1.5">
                        <span className="font-mono text-xs text-gray-400">{fmtPct(b.model_prob)}</span>
                        {b.ev != null && (
                          <span className={`font-mono text-xs ${clvColor(b.ev)}`}>{fmtSignedPct(b.ev)}</span>
                        )}
                      </div>
                    )}
                  </TableCell>
                  <TableCell
                    className={`py-3 pr-5 text-right font-mono text-sm whitespace-nowrap ${pnlColor(b.profit_loss)}`}
                  >
                    {fmtPnlExact(b.profit_loss)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
      {sorted.length > BET_LOG_PAGE_SIZE && (
        <div className="flex items-center justify-between mt-3 px-1">
          <p className="text-xs text-gray-600">
            Showing {page * BET_LOG_PAGE_SIZE + 1}–{Math.min((page + 1) * BET_LOG_PAGE_SIZE, sorted.length)} of {sorted.length} bets
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="rounded border border-[#262626] px-2.5 py-1 text-xs text-gray-400 hover:text-white hover:border-gray-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              Prev
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="rounded border border-[#262626] px-2.5 py-1 text-xs text-gray-400 hover:text-white hover:border-gray-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function PerformancePage() {
  const { accessToken, email } = useAuth()
  const [season, setSeason] = useState<Season>(2026)
  const [includeDegraded, setIncludeDegraded] = useState(false)
  const seasonParam = season != null ? `?season=${season}` : ""

  const { data: betsData } = useQuery<PerformanceBetsResponse>({
    queryKey: ["perf-bets", season],
    queryFn: () => apiFetch(`/performance/bets${seasonParam}`, {}, accessToken),
  })

  const { data: modelData, isFetching: modelFetching } = useQuery<ModelMetricsResponse>({
    queryKey: ["perf-model", season, includeDegraded],
    queryFn: () => {
      const params = new URLSearchParams()
      if (season != null) params.set("season", String(season))
      if (includeDegraded) params.set("include_degraded", "true")
      const qs = params.toString() ? `?${params.toString()}` : ""
      return apiFetch(`/performance/model${qs}`, {}, accessToken)
    },
  })

  const { data: bankrollData } = useQuery<BankrollData>({
    queryKey: ["bankroll"],
    queryFn: () => apiFetch("/users/bankroll", {}, accessToken),
    enabled: !!accessToken,
  })

  const summary = useMemo(() => deriveSummary(betsData), [betsData])
  const bets = betsData?.bets ?? []
  const bankrollGrowth = bankrollData?.overall_growth ?? null

  return (
    <AuthGuard>
      <div className="min-h-screen bg-[#0a0a0a] font-sans">
        <Nav authenticated activeLink="performance" userEmail={email} />
        <main className="mx-auto max-w-6xl px-4 pb-20">
          {/* Page header */}
          <div className="flex flex-col gap-4 pt-10 pb-6 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-white md:text-4xl">
                Performance
              </h1>
              <p className="mt-2 text-sm text-gray-400">
                Your bet results and model skill metrics.
              </p>
            </div>
            <SeasonSelector season={season} onChange={setSeason} />
          </div>

          {/* Summary tiles */}
          <StatTiles summary={summary} bankrollGrowth={bankrollGrowth} />

          {/* Per-book bankroll breakdown — hidden until ≥1 book+deposit */}
          {bankrollData?.per_book_growth && (
            <div className="mt-5">
              <PerBookBreakdown perBook={bankrollData.per_book_growth} />
            </div>
          )}

          {/* Model skill strip */}
          <div className={`mt-5 transition-opacity duration-200 ${modelFetching ? "opacity-50" : "opacity-100"}`}>
            <ModelSkillStrip
              data={modelData}
              season={season}
              includeDegraded={includeDegraded}
              onToggleDegraded={() => setIncludeDegraded(v => !v)}
            />
          </div>

          {/* P&L curve */}
          <div className="mt-5">
            <PLCurve bets={bets} />
          </div>

          {/* Breakdown tabs */}
          <div className="mt-5">
            <BreakdownTabs bets={bets} />
          </div>

          {/* Bet log */}
          <div className="mt-8">
            <BetLogTable bets={bets} />
          </div>
        </main>
      </div>
    </AuthGuard>
  )
}
