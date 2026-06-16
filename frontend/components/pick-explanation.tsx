"use client"

import { Info } from "lucide-react"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

// ---------------------------------------------------------------------------
// Types mirroring PickExplanationPayload from the API
// ---------------------------------------------------------------------------

export type PickDriver = {
  feature: string
  label: string
  family: string
  family_key: string
  contribution: number
  direction: "increases" | "decreases"
  toward: string
}

export type PickExplanationTarget = {
  method: string
  units: string
  base_value: number | null
  prediction: number | null
  toward: string
  drivers: PickDriver[]
  note: string | null
}

export type PickExplanationPayload = {
  served_tier: string | null
  basis: string
  disclaimer: string
  targets: Record<string, PickExplanationTarget>
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const FAMILY_ORDER: Record<string, number> = {
  "Starting pitcher": 0,
  "Bullpen": 1,
  "Team offense": 2,
  "Lineup offense": 3,
  "Platoon matchup": 4,
  "Team rating": 5,
  "Run-based rating": 6,
  "Park / weather / umpire": 7,
  "Schedule / rest": 8,
  "Market": 9,
}

function groupByFamily(drivers: PickDriver[]): Map<string, PickDriver[]> {
  const map = new Map<string, PickDriver[]>()
  for (const d of drivers) {
    if (!map.has(d.family)) map.set(d.family, [])
    map.get(d.family)!.push(d)
  }
  // Sort groups by canonical order, unknowns last
  const sorted = new Map(
    [...map.entries()].sort(([a], [b]) => {
      const oa = FAMILY_ORDER[a] ?? 99
      const ob = FAMILY_ORDER[b] ?? 99
      return oa - ob
    })
  )
  return sorted
}

function maxAbsContrib(drivers: PickDriver[]): number {
  return Math.max(...drivers.map((d) => Math.abs(d.contribution)), 0.001)
}

// ---------------------------------------------------------------------------
// DriverBar — one signed bar for a single driver
// ---------------------------------------------------------------------------

function DriverBar({
  driver,
  scale,
}: {
  driver: PickDriver
  scale: number
}) {
  const isPos = driver.direction === "increases"
  // Bar width as % of half-track (max 50%)
  const pct = Math.min((Math.abs(driver.contribution) / scale) * 50, 50)
  const colorClass = isPos ? "bg-[#10b981]" : "bg-[#f87171]"

  return (
    <div className="py-1.5 border-b border-[#1a1a1a] last:border-0">
      <div className="flex items-center justify-between mb-1 gap-2">
        <span className="text-xs text-gray-300 leading-tight truncate max-w-[70%]">
          {driver.label}
        </span>
        <span className={`text-[10px] font-semibold shrink-0 ${isPos ? "text-[#10b981]" : "text-[#f87171]"}`}>
          {isPos ? "▲" : "▼"} {driver.direction} {driver.toward}
        </span>
      </div>
      <div className="relative h-1.5 bg-[#1e1e1e] rounded-full overflow-hidden">
        <div className="absolute top-0 bottom-0 left-1/2 w-px bg-[#333]" />
        <div
          className={`absolute top-0 bottom-0 rounded-full ${colorClass}`}
          style={
            isPos
              ? { left: "50%", width: `${pct}%` }
              : { right: "50%", width: `${pct}%` }
          }
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// PickExplanationSection — full drivers view for the game detail page
// ---------------------------------------------------------------------------

export function PickExplanationSection({
  explanation,
  marketType,
}: {
  explanation: PickExplanationPayload
  marketType: "h2h" | "totals" | string
}) {
  const targetKey = marketType === "h2h" ? "home_win" : "total_runs"
  const primaryTarget = explanation.targets?.[targetKey]
  // Fall back to whichever target has data
  const target = primaryTarget
    ?? explanation.targets?.["home_win"]
    ?? explanation.targets?.["total_runs"]

  if (!target || !target.drivers?.length) {
    return (
      <p className="text-xs text-gray-600">
        {target?.note ?? "Feature attribution not available for this game."}
      </p>
    )
  }

  const drivers = target.drivers

  const scale = maxAbsContrib(drivers)
  const grouped = groupByFamily(drivers)

  return (
    <div className="space-y-4">
      {/* Disclaimer */}
      <div className="flex items-start gap-2 rounded-lg bg-[#0d0d0d] border border-[#1e1e1e] px-3 py-2.5">
        <Info className="h-3 w-3 text-gray-600 mt-0.5 shrink-0" />
        <p className="text-[11px] leading-relaxed text-gray-500">
          {explanation.disclaimer ||
            "Shows which inputs most moved our model's prediction — explains model reasoning, not a betting edge."}
        </p>
      </div>

      {/* Bar chart legend */}
      <div className="flex items-center gap-4 text-[10px] text-gray-600">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-1.5 rounded bg-[#10b981]" />
          pushes {target?.toward ?? "prediction"} up
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-1.5 rounded bg-[#f87171]" />
          pushes it down
        </span>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="cursor-help flex items-center gap-0.5">
              <Info className="h-3 w-3" />
              units
            </span>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-[220px] text-xs leading-relaxed">
            {marketType === "h2h"
              ? "Bar length shows relative influence on the win-probability prediction. Contributions are in log-odds space — bar size is for comparison only."
              : "Bar length shows relative influence on the projected run total. Larger bar = stronger pull on the model's forecast."}
          </TooltipContent>
        </Tooltip>
      </div>

      {/* Grouped drivers */}
      {[...grouped.entries()].map(([family, fDrivers]) => (
        <div key={family}>
          <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-widest mb-1">
            {family}
          </p>
          <div className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-1">
            {fDrivers.map((d) => (
              <DriverBar key={d.feature} driver={d} scale={scale} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// MiniDriverList — compact 2-3 driver list for the home page card
// ---------------------------------------------------------------------------

export function MiniDriverList({ drivers }: { drivers: PickDriver[] }) {
  if (!drivers.length) return null
  return (
    <ul className="mt-2 space-y-1">
      {drivers.map((d) => (
        <li key={d.feature} className="flex items-center gap-1.5 text-xs text-gray-500">
          <span className={d.direction === "increases" ? "text-[#10b981]" : "text-[#f87171]"}>
            {d.direction === "increases" ? "▲" : "▼"}
          </span>
          <span>{d.label}</span>
          <span className="text-gray-700">· {d.family}</span>
        </li>
      ))}
    </ul>
  )
}

// ---------------------------------------------------------------------------
// ServedTierBadge — shows pre-lineup vs post-lineup context
// ---------------------------------------------------------------------------

export function ServedTierBadge({ tier }: { tier: string | null | undefined }) {
  if (!tier || tier === "backfill") return null
  const isPreLineup = tier === "pre_lineup"
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-widest border ${
        isPreLineup
          ? "bg-amber-500/10 text-amber-400 border-amber-500/25"
          : "bg-[#10b981]/10 text-[#10b981] border-[#10b981]/25"
      }`}
    >
      {isPreLineup ? "Pre-lineup" : "Post-lineup"}
    </span>
  )
}
