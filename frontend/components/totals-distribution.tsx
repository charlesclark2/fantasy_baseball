"use client"

// ---------------------------------------------------------------------------
// Story E2.7 — Distribution UX
// Renders the CALIBRATED predictive-total distribution for a game: the game-total density with the
// market line + shaded favorable mass, the P(over) / 80% interval, the run-diff (home−away) view,
// and the team-total + alt-line P(over) ladders. Consumes the served `totals_distribution` blob
// (write_serving_store → picks.py); the app NEVER recomputes a distribution.
//
// HONEST FRAMING (best_alpha=0, non-negotiable): this is a transparency surface — "our calibrated
// view of this total" — NOT an edge / value / win-rate claim. E2.6's derivative gate closed as a
// confirmed clean null (no team-total / alt-line beat its close), so nothing here is a bet rec.
// ---------------------------------------------------------------------------

import { Info } from "lucide-react"
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

// ---------------------------------------------------------------------------
// Types — mirror app/backend/models/picks.py TotalsDistribution
// ---------------------------------------------------------------------------

export type DistLadderPoint = { line: number; p_over: number }
export type DistPmfPoint = { x: number; p: number }

export type TotalDistributionData = {
  mu: number
  quantiles: Record<string, number>
  pmf: DistPmfPoint[]
  ci80: number[]
  market_line: number | null
  p_over: number | null
}

export type RunDiffDistributionData = {
  mu: number
  quantiles: Record<string, number>
  pmf: DistPmfPoint[]
  p_home: number
}

export type TeamTotalDistributionData = {
  line: number
  p_over: number
  mu: number
  ladder: DistLadderPoint[]
}

export type TotalsDistributionData = {
  version: string | null
  total: TotalDistributionData
  run_diff: RunDiffDistributionData
  team_totals: { home: TeamTotalDistributionData; away: TeamTotalDistributionData }
  alt_totals: DistLadderPoint[]
}

// ---------------------------------------------------------------------------
// Palette (match the page conventions)
// ---------------------------------------------------------------------------
const ACCENT = "#10b981" // green
const MUTED = "#6b7280" // gray text
const MARKET = "#f59e0b" // orange (market line)
const GRID = "#1e1e1e"

const fmtPct = (n: number | null | undefined) =>
  n == null || Number.isNaN(n) ? "—" : `${(n * 100).toFixed(0)}%`
const fmtRuns = (n: number | null | undefined) =>
  n == null || Number.isNaN(n) ? "—" : n.toFixed(1)

function DensityTooltip({ active, payload, unit }: any) {
  if (!active || !payload?.length) return null
  const pt = payload[0]?.payload
  if (!pt) return null
  return (
    <div className="rounded-md border border-[#2a2a2a] bg-[#0a0a0a] px-2.5 py-1.5 text-[11px] text-gray-300">
      {pt.x} {unit} · <span className="text-white">{(pt.p * 100).toFixed(1)}%</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// DensityChart — the exact probability mass function (P(outcome == k) at each integer k) as a smooth
// bell, with the market line, the model's projected mean, and the leaned mass shaded. A game total /
// run margin is an INTEGER count, so we plot the served PMF directly — no continuous-density
// reconstruction (that oscillates on the integer lattice into a sawtooth).
// ---------------------------------------------------------------------------
function DensityChart({
  pmf,
  refLine,
  meanLine,
  refLabel,
  shadeSide,
  unit,
  ariaLabel,
}: {
  pmf: DistPmfPoint[]
  refLine: number | null // market line (over/under boundary), orange dashed
  meanLine: number | null // the model's projected mean, green solid
  refLabel: string
  shadeSide: "over" | "under" | null // which side of refLine to shade (the model's lean)
  unit: string
  ariaLabel: string
}) {
  if (!pmf?.length) return null
  const xs = pmf.map((p) => p.x)
  const xMin = Math.min(...xs)
  const xMax = Math.max(...xs)

  return (
    <div role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height={150}>
        <AreaChart data={pmf} margin={{ top: 12, right: 8, left: 8, bottom: 4 }}>
          <defs>
            <linearGradient id={`grad-${unit}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={ACCENT} stopOpacity={0.35} />
              <stop offset="100%" stopColor={ACCENT} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
          <XAxis
            dataKey="x"
            type="number"
            domain={[xMin, xMax]}
            tick={{ fill: MUTED, fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) => v.toFixed(0)}
          />
          <YAxis hide domain={[0, "dataMax"]} />
          <RechartsTooltip content={<DensityTooltip unit={unit} />} cursor={{ stroke: MUTED }} />
          {/* Shade the model's leaned mass (transparency, not a rec). */}
          {refLine != null && shadeSide === "over" && (
            <ReferenceArea x1={refLine} x2={xMax} fill={ACCENT} fillOpacity={0.08} />
          )}
          {refLine != null && shadeSide === "under" && (
            <ReferenceArea x1={xMin} x2={refLine} fill={ACCENT} fillOpacity={0.08} />
          )}
          <Area
            type="monotone"
            dataKey="p"
            stroke={ACCENT}
            strokeWidth={2}
            fill={`url(#grad-${unit})`}
            isAnimationActive={false}
            dot={false}
          />
          {/* Model's projected mean — where we think it lands. */}
          {meanLine != null && (
            <ReferenceLine
              x={meanLine}
              stroke={ACCENT}
              strokeWidth={1.5}
              label={{ value: `Proj ${meanLine.toFixed(1)}`, position: "top", fill: ACCENT, fontSize: 10 }}
            />
          )}
          {/* Market line / even. */}
          {refLine != null && (
            <ReferenceLine
              x={refLine}
              stroke={MARKET}
              strokeWidth={1.5}
              strokeDasharray="4 3"
              label={{ value: refLabel, position: "insideTopRight", fill: MARKET, fontSize: 10 }}
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

// ---------------------------------------------------------------------------
// LadderRow — one line + its P(over) as a horizontal bar (matches the DriverBar idiom).
// ---------------------------------------------------------------------------
function LadderRow({ line, pOver, highlight }: { line: number; pOver: number; highlight?: boolean }) {
  const pct = Math.max(0, Math.min(1, pOver)) * 100
  return (
    <div className="flex items-center gap-2 py-1">
      <span className={`w-10 shrink-0 text-right text-[11px] tabular-nums ${highlight ? "text-white font-semibold" : "text-gray-400"}`}>
        {line.toFixed(1)}
      </span>
      <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-[#1e1e1e]">
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ width: `${pct}%`, backgroundColor: highlight ? ACCENT : "#0e7a5c" }}
        />
      </div>
      <span className="w-9 shrink-0 text-right text-[11px] tabular-nums text-gray-300">{fmtPct(pOver)}</span>
    </div>
  )
}

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2.5">
      <div className="flex items-center gap-1 text-[10px] uppercase tracking-widest text-gray-600">
        {label}
        {hint && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="cursor-help">
                <Info className="h-2.5 w-2.5" />
              </span>
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-[240px] text-xs leading-relaxed">
              {hint}
            </TooltipContent>
          </Tooltip>
        )}
      </div>
      <div className="mt-0.5 text-lg font-semibold tabular-nums text-white">{value}</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// TotalsDistributionPanel — the full "how confident" panel beside the SHAP "why" drivers.
// ---------------------------------------------------------------------------
export function TotalsDistributionPanel({
  dist,
  homeTeam,
  awayTeam,
}: {
  dist: TotalsDistributionData
  homeTeam?: string | null
  awayTeam?: string | null
}) {
  const { total, run_diff, team_totals, alt_totals } = dist
  const line = total.market_line
  const pOver = total.p_over
  const leanOver = pOver != null ? pOver >= 0.5 : null
  const shadeSide = line == null || leanOver == null ? null : leanOver ? "over" : "under"
  const ci = total.ci80 && total.ci80.length === 2 ? total.ci80 : null

  return (
    <div className="space-y-5">
      {/* honest-framing note */}
      <div className="flex items-start gap-2 rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2.5">
        <Info className="mt-0.5 h-3 w-3 shrink-0 text-gray-600" />
        <p className="text-[11px] leading-relaxed text-gray-500">
          Our model&apos;s calibrated view of how this game&apos;s scoring could land — a distribution, not a
          prediction of certainty. Shown for transparency only; our models have no demonstrated market edge
          (best alpha = 0), so this is context, not a bet recommendation.
        </p>
      </div>

      {/* headline stats */}
      <div className="grid grid-cols-3 gap-2">
        <StatTile
          label="Proj. total"
          value={`${fmtRuns(total.mu)}`}
          hint="The model's expected combined runs for the game (mean of the predictive distribution)."
        />
        <StatTile
          label="80% range"
          value={ci ? `${fmtRuns(ci[0])}–${fmtRuns(ci[1])}` : "—"}
          hint="The 80% predictive interval: the model puts ~80% of the probability mass for the final total between these two run values. Single games are high-variance — the range is wide on purpose."
        />
        <StatTile
          label={line != null ? `P(over ${line.toFixed(1)})` : "P(over)"}
          value={fmtPct(pOver)}
          hint={
            line != null
              ? `The model's probability the combined total lands strictly above the ${line.toFixed(1)} line. A calibrated read, not an edge — compare it to the market's own de-vigged number.`
              : "No market total line was available for this game, so the over probability is not anchored to a line."
          }
        />
      </div>

      {/* game-total density */}
      <div>
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-gray-600">
          Predicted game total (runs)
        </p>
        <DensityChart
          pmf={total.pmf}
          refLine={line}
          meanLine={total.mu}
          refLabel={line != null ? `Line ${line.toFixed(1)}` : ""}
          shadeSide={shadeSide}
          unit="runs"
          ariaLabel={`Predicted game total distribution${line != null ? `, market line ${line.toFixed(1)}` : ""}`}
        />
        {line != null && (
          <p className="mt-1 text-[10px] text-gray-600">
            <span className="text-[#f59e0b]">Dashed line</span> = market total {line.toFixed(1)}.
            Shaded mass = the {leanOver ? "over" : "under"} side the model leans ({fmtPct(pOver)}).
          </p>
        )}
      </div>

      {/* run-diff density */}
      <div>
        <div className="mb-1 flex items-center justify-between">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-gray-600">
            Run margin (home − away)
          </p>
          <span className="text-[11px] text-gray-400">
            P({homeTeam || "home"} outscores {awayTeam || "away"}){" "}
            <span className="font-semibold text-gray-200">{fmtPct(run_diff.p_home)}</span>
          </span>
        </div>
        <DensityChart
          pmf={run_diff.pmf}
          refLine={0}
          meanLine={null}
          refLabel="Even"
          shadeSide={run_diff.p_home >= 0.5 ? "over" : "under"}
          unit="margin"
          ariaLabel="Predicted run-margin distribution (home minus away)"
        />
        <p className="mt-1 text-[10px] text-gray-600">
          Mass right of <span className="text-[#f59e0b]">even</span> = the home side wins on the scoreboard —
          the distributional view behind the moneyline lean.
        </p>
      </div>

      {/* team totals + alt-line ladders */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-gray-600">
            Team totals · P(over)
          </p>
          <div className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2">
            <p className="text-[11px] text-gray-400">{homeTeam || "Home"} <span className="text-gray-600">(proj {fmtRuns(team_totals.home.mu)})</span></p>
            {team_totals.home.ladder.map((pt) => (
              <LadderRow key={`h-${pt.line}`} line={pt.line} pOver={pt.p_over} highlight={pt.line === team_totals.home.line} />
            ))}
            <div className="my-1 border-t border-[#1a1a1a]" />
            <p className="text-[11px] text-gray-400">{awayTeam || "Away"} <span className="text-gray-600">(proj {fmtRuns(team_totals.away.mu)})</span></p>
            {team_totals.away.ladder.map((pt) => (
              <LadderRow key={`a-${pt.line}`} line={pt.line} pOver={pt.p_over} highlight={pt.line === team_totals.away.line} />
            ))}
          </div>
        </div>
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-gray-600">
            Alt game totals · P(over)
          </p>
          <div className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2">
            {alt_totals.map((pt) => (
              <LadderRow key={`alt-${pt.line}`} line={pt.line} pOver={pt.p_over} highlight={line != null && pt.line === line} />
            ))}
          </div>
        </div>
      </div>

      <p className="text-[10px] leading-relaxed text-gray-700">
        Ladders read straight off the same calibrated distribution — the probability the total (or a team&apos;s
        runs) finishes above each line. No line here cleared a market-edge test; they&apos;re a transparency
        view of the model&apos;s spread, not value picks.
      </p>
    </div>
  )
}
