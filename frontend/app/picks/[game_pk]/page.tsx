"use client"

import { useParams } from "next/navigation"
import Link from "next/link"
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts"
import {
  ArrowUp,
  ArrowDown,
  ArrowRight,
  CheckCircle2,
  XCircle,
  LogOut,
  Sun,
  ChevronLeft,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ProbabilityBar } from "@/components/probability-bar"

// ---------------------------------------------------------------------------
// TODO: replace with useQuery hook — GET /picks/today filtered by game_pk
// ---------------------------------------------------------------------------
const MOCK_DATA = {
  game: {
    matchup: "HOU @ NYM",
    date: "Tuesday June 3, 2026",
    time: "7:10 PM ET",
    venue: "Minute Maid Park",
    weather: "84°F Partly Cloudy",
    market: "Totals Over 8.5",
    edge: "+4.2%",
    conviction: "HIGH",
    modelProb: 0.583,
    marketProb: 0.541,
  },
  ciLow: 0.48,
  ciHigh: 0.61,
  distributionData: [
    { runs: 0, prob: 0.008 },
    { runs: 1, prob: 0.018 },
    { runs: 2, prob: 0.034 },
    { runs: 3, prob: 0.055 },
    { runs: 4, prob: 0.074 },
    { runs: 5, prob: 0.089 },
    { runs: 6, prob: 0.098 },
    { runs: 7, prob: 0.103 },
    { runs: 8, prob: 0.101 },
    { runs: 9, prob: 0.096 },
    { runs: 10, prob: 0.088 },
    { runs: 11, prob: 0.076 },
    { runs: 12, prob: 0.063 },
    { runs: 13, prob: 0.050 },
    { runs: 14, prob: 0.038 },
    { runs: 15, prob: 0.028 },
    { runs: 16, prob: 0.020 },
    { runs: 17, prob: 0.013 },
    { runs: 18, prob: 0.009 },
    { runs: 19, prob: 0.006 },
    { runs: 20, prob: 0.004 },
  ],
  signals: [
    { name: "Run Environment", direction: "bullish", value: "+0.8 runs vs avg", confidence: "High Confidence" },
    { name: "Offense HOU", direction: "bullish", value: "xwOBA +0.031 advantage", confidence: "High Confidence" },
    { name: "Offense NYM", direction: "neutral", value: "Near league average", confidence: "Moderate" },
    { name: "Starter HOU", direction: "bullish", value: "xFIP 3.41 — above avg suppression risk", confidence: "Moderate" },
    { name: "Starter NYM", direction: "bearish", value: "xFIP 3.89 — elevated ERA risk", confidence: "High Confidence" },
    { name: "Bullpen HOU", direction: "neutral", value: "Avg leverage, rested", confidence: "Moderate" },
    { name: "Bullpen NYM", direction: "bearish", value: "High leverage usage last 3 days", confidence: "Low Confidence" },
    { name: "Matchup", direction: "bullish", value: "HOU bats vs NYM LHP favorable", confidence: "High Confidence" },
  ],
  gateCriteria: [
    { fired: true, label: "Edge > 3% threshold", detail: "model edge of +4.2% clears the minimum gate" },
    { fired: true, label: "Full credible interval above market line", detail: "80% CI from 48% to 61% sits entirely above 54.1%" },
    { fired: true, label: "Signal completeness ≥ 0.80", detail: "all 8 sub-model signals present and fresh" },
    { fired: true, label: "Conviction score ≥ 0.65", detail: "gate score of 0.81 clears the HIGH conviction threshold" },
    { fired: false, label: "CLV meta-model gate", detail: "insufficient historical data at this line for full CLV prior (needs 50+ samples, have 31)" },
  ],
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Split distribution into under (runs <= 8) and over (runs >= 9) series,
 *  with a shared overlap point at runs=8 to make the areas join cleanly. */
const underData = MOCK_DATA.distributionData.filter((d) => d.runs <= 8)
const overData = MOCK_DATA.distributionData.filter((d) => d.runs >= 8)

function ConfidenceBadge({ confidence }: { confidence: string }) {
  if (confidence === "High Confidence") {
    return (
      <Badge variant="outline" className="border-[#10b981] text-[#10b981] text-[10px] font-semibold px-1.5 py-0">
        High Confidence
      </Badge>
    )
  }
  if (confidence === "Moderate") {
    return (
      <Badge variant="outline" className="border-[#f59e0b] text-[#f59e0b] text-[10px] font-semibold px-1.5 py-0">
        Moderate
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="border-gray-600 text-gray-500 text-[10px] font-semibold px-1.5 py-0">
      Low Confidence
    </Badge>
  )
}

function DirectionIcon({ direction }: { direction: string }) {
  if (direction === "bullish") return <ArrowUp className="h-4 w-4 text-[#10b981]" />
  if (direction === "bearish") return <ArrowDown className="h-4 w-4 text-[#ef4444]" />
  return <ArrowRight className="h-4 w-4 text-gray-500" />
}

function DistributionTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-[#262626] bg-[#141414] px-3 py-2 shadow-xl">
      <p className="text-xs text-gray-400 mb-0.5">{label} total runs</p>
      <p className="text-sm font-semibold font-mono text-white">
        {(payload[0].value * 100).toFixed(1)}%
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Navbar — neither sub-nav link is active on this page
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
      {/* Sub-nav — neither active on this drill-down page */}
      <div className="mx-auto flex max-w-6xl gap-6 px-4 pb-0">
        <Link
          href="/dashboard"
          className="border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
        >
          Dashboard
        </Link>
        <Link
          href="/performance"
          className="border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
        >
          Performance
        </Link>
      </div>
    </nav>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function PickDetailPage() {
  useParams() // game_pk available via params.game_pk — not displayed
  const { game, ciLow, ciHigh, distributionData, signals, gateCriteria } = MOCK_DATA

  return (
    <div className="min-h-screen bg-[#0a0a0a] font-sans">
      <Navbar />

      <main className="mx-auto max-w-6xl px-4 py-8 space-y-6">

        {/* Back navigation */}
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
        >
          <ChevronLeft className="h-4 w-4" />
          Back to Dashboard
        </Link>

        {/* ----------------------------------------------------------------- */}
        {/* 1. Game header card                                                */}
        {/* ----------------------------------------------------------------- */}
        <div className="rounded-xl border border-[#262626] bg-[#141414] px-6 py-5">
          <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">

            {/* Left — matchup + datetime */}
            <div className="flex flex-col gap-1">
              <h1 className="text-2xl font-bold tracking-tight text-white">
                {game.matchup}
              </h1>
              <p className="text-sm text-gray-500">
                {game.date} &middot; {game.time}
              </p>
            </div>

            {/* Center — venue + weather */}
            <div className="flex items-center gap-2 text-sm text-gray-500 md:text-center">
              <Sun className="h-4 w-4 flex-shrink-0 text-[#f59e0b]" />
              <span>{game.venue} &middot; {game.weather}</span>
            </div>

            {/* Right — chips */}
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="border-[#262626] text-gray-400 text-xs font-medium">
                  {game.market}
                </Badge>
                <Badge className="bg-[#10b981]/15 text-[#10b981] border border-[#10b981]/30 text-xs font-semibold">
                  Edge {game.edge}
                </Badge>
                <Badge className="bg-[#10b981] text-[#0a0a0a] text-xs font-bold uppercase tracking-widest">
                  HIGH
                </Badge>
              </div>
              <p className="text-xs text-gray-500">
                Model{" "}
                <span className="font-mono text-white">{(game.modelProb * 100).toFixed(1)}%</span>
                {" "}vs Market{" "}
                <span className="font-mono text-gray-400">{(game.marketProb * 100).toFixed(1)}%</span>
              </p>
            </div>
          </div>
        </div>

        {/* ----------------------------------------------------------------- */}
        {/* 2. Distribution chart card                                         */}
        {/* ----------------------------------------------------------------- */}
        <div className="rounded-xl border border-[#262626] bg-[#141414] px-6 py-5">
          <div className="mb-4 flex items-start justify-between gap-4">
            <h2 className="text-sm font-semibold text-white">
              Run Distribution &mdash; P(Over 8.5)
            </h2>
            <div className="text-right flex-shrink-0">
              <p className="text-xs text-gray-500 mb-0.5">P(Over)</p>
              <p className="text-2xl font-bold font-mono text-[#10b981]">58.3%</p>
            </div>
          </div>

          <ResponsiveContainer width="100%" height={220}>
            <AreaChart
              margin={{ top: 8, right: 8, left: -16, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#262626" vertical={false} />
              <XAxis
                dataKey="runs"
                type="number"
                domain={[0, 20]}
                ticks={[0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20]}
                tick={{ fill: "#6b7280", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                dy={6}
                allowDuplicatedCategory={false}
              />
              <YAxis
                tick={{ fill: "#6b7280", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                width={36}
              />
              <Tooltip content={<DistributionTooltip />} />

              {/* Under area — gray (runs 0–8) */}
              <Area
                data={underData}
                type="monotone"
                dataKey="prob"
                stroke="#6b7280"
                strokeWidth={1.5}
                fill="#6b7280"
                fillOpacity={0.2}
                dot={false}
                activeDot={{ r: 3, fill: "#6b7280" }}
                legendType="none"
              />

              {/* Over area — emerald (runs 8–20) */}
              <Area
                data={overData}
                type="monotone"
                dataKey="prob"
                stroke="#10b981"
                strokeWidth={1.5}
                fill="#10b981"
                fillOpacity={0.5}
                dot={false}
                activeDot={{ r: 3, fill: "#10b981" }}
                legendType="none"
              />

              {/* Bovada line at x=8 */}
              <ReferenceLine
                x={8}
                stroke="#f59e0b"
                strokeDasharray="4 3"
                label={{
                  value: "Bovada Line 8.5",
                  position: "insideTopRight",
                  fill: "#f59e0b",
                  fontSize: 10,
                  dy: -4,
                  dx: 4,
                }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* ----------------------------------------------------------------- */}
        {/* 3. ProbabilityBar card                                             */}
        {/* ----------------------------------------------------------------- */}
        <div className="rounded-xl border border-[#262626] bg-[#141414] px-6 py-5">
          <h2 className="mb-5 text-sm font-semibold text-white">Credible Interval</h2>
          <ProbabilityBar
            ciLow={ciLow}
            ciHigh={ciHigh}
            modelProb={game.modelProb}
            marketProb={game.marketProb}
            showLabels={true}
            showHighConviction={true}
          />
          <p className="mt-5 text-xs leading-relaxed text-gray-500">
            The 80% credible interval represents the range where the true probability is likely to
            fall. When the entire interval sits above the market line, the model fires the
            high-conviction gate.
          </p>
        </div>

        {/* ----------------------------------------------------------------- */}
        {/* 4. Signal breakdown grid                                           */}
        {/* ----------------------------------------------------------------- */}
        <div className="rounded-xl border border-[#262626] bg-[#141414] px-6 py-5">
          <h2 className="mb-5 text-sm font-semibold text-white">Signal Breakdown</h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {signals.map((signal) => (
              <div
                key={signal.name}
                className="flex flex-col gap-2 rounded-lg border border-[#262626] bg-[#0a0a0a] px-4 py-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold text-white leading-tight">{signal.name}</p>
                  <DirectionIcon direction={signal.direction} />
                </div>
                <p className="text-xs text-gray-500 leading-relaxed">{signal.value}</p>
                <div className="mt-auto pt-1">
                  <ConfidenceBadge confidence={signal.confidence} />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ----------------------------------------------------------------- */}
        {/* 5. Gate criteria checklist                                         */}
        {/* ----------------------------------------------------------------- */}
        <div className="rounded-xl border border-[#262626] bg-[#141414] px-6 py-5">
          <h2 className="mb-5 text-sm font-semibold text-white">Why This Pick</h2>
          <ul className="space-y-3">
            {gateCriteria.map((item) => (
              <li key={item.label} className="flex items-start gap-3">
                {item.fired ? (
                  <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-[#10b981]" />
                ) : (
                  <XCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-gray-600" />
                )}
                <p className={`text-sm leading-relaxed ${item.fired ? "text-gray-300" : "text-gray-600"}`}>
                  <span className="font-medium">{item.label}</span>
                  {" — "}
                  {item.detail}
                </p>
              </li>
            ))}
          </ul>
        </div>

        {/* ----------------------------------------------------------------- */}
        {/* 6. Disclaimer                                                      */}
        {/* ----------------------------------------------------------------- */}
        <p className="pb-8 text-xs leading-relaxed text-gray-600">
          This analysis is generated by a quantitative model and does not constitute financial
          advice. Past performance does not guarantee future results. You are solely responsible
          for any wagers placed.
        </p>

      </main>
    </div>
  )
}
