"use client"

import { useState, useRef, useCallback } from "react"

// ---------------------------------------------------------------------------
// Types (mirrors e13_10_sample_overlay.json schema_version 2.0)
// ---------------------------------------------------------------------------

export type PitchGroup = "all" | "fastball" | "breaking" | "offspeed"

export interface ZoneCell {
  pitch_group: PitchGroup
  ix: number
  iz: number
  x_ft: number
  z_norm: number
  z_ft: number
  batter_run_value: number | null
  batter_whiff: number | null
  batter_xwoba: number | null
  pitcher_usage_freq: number
  pitcher_loc: { x_ft: number; z_ft: number }
}

export interface ZoneOverlayData {
  schema_version: string
  as_of_date: string
  matchup: {
    batter_id: number
    batter_name: string
    b_hand: string
    pitcher_id: number
    pitcher_name: string
    p_hand: string
  }
  strike_zone: { sz_top: number; sz_bot: number }
  grid: {
    nx: number
    nz: number
    x_edges: number[]
    z_norm_edges: number[]
    called_zone: { x_half_ft: number; z_norm: [number, number] }
  }
  pitch_groups: string[]
  overlap_scalar: number
  overlap_units: string
  is_cold_start: { batter: boolean; pitcher: boolean }
  cells: ZoneCell[]
}

// ---------------------------------------------------------------------------
// SVG coordinate system
// Grid covers x ∈ [-1.4, 1.4] ft, z_norm ∈ [-0.25, 1.25]
// iz=0 is BOTTOM of zone, SVG y=0 is TOP → must invert z
// ---------------------------------------------------------------------------

const SVG_W = 220
const SVG_H = 250
const X_MIN = -1.4
const X_MAX = 1.4
const Z_MIN = -0.25
const Z_MAX = 1.25

function toSvgX(x_ft: number): number {
  return ((x_ft - X_MIN) / (X_MAX - X_MIN)) * SVG_W
}

function toSvgY(z_norm: number): number {
  return (1 - (z_norm - Z_MIN) / (Z_MAX - Z_MIN)) * SVG_H
}

function zFtToNorm(z_ft: number, sz_bot: number, sz_top: number): number {
  if (sz_top === sz_bot) return 0.5
  return (z_ft - sz_bot) / (sz_top - sz_bot)
}

// ---------------------------------------------------------------------------
// Color scale — diverging centered at 0, dark-theme palette
// ---------------------------------------------------------------------------

function lerpColor(
  from: [number, number, number],
  to: [number, number, number],
  t: number,
): string {
  const r = Math.round(from[0] + (to[0] - from[0]) * t)
  const g = Math.round(from[1] + (to[1] - from[1]) * t)
  const b = Math.round(from[2] + (to[2] - from[2]) * t)
  return `rgb(${r},${g},${b})`
}

const NEUTRAL_RGB: [number, number, number] = [38, 38, 38]
const HOT_RGB: [number, number, number] = [239, 68, 68]    // red-500
const COLD_RGB: [number, number, number] = [59, 130, 246]  // blue-500

function valueToColor(v: number | null, vmax: number): string {
  if (v == null) return "#111111"
  const t = Math.min(1, Math.abs(v) / vmax)
  return v >= 0 ? lerpColor(NEUTRAL_RGB, HOT_RGB, t) : lerpColor(NEUTRAL_RGB, COLD_RGB, t)
}

function computeVmax(cells: ZoneCell[], group: PitchGroup): number {
  const vals = cells
    .filter((c) => c.pitch_group === group && c.batter_run_value != null)
    .map((c) => Math.abs(c.batter_run_value!))
  if (vals.length === 0) return 0.06
  vals.sort((a, b) => a - b)
  const idx = Math.min(Math.ceil(vals.length * 0.95), vals.length - 1)
  return Math.max(vals[idx], 0.01)
}

// ---------------------------------------------------------------------------
// Formatting helpers for tooltip
// ---------------------------------------------------------------------------

function fmtRV(v: number | null): string {
  if (v == null) return "—"
  return (v >= 0 ? "+" : "") + v.toFixed(4) + " runs/pitch"
}

function fmtPct(v: number | null): string {
  if (v == null) return "—"
  return (v * 100).toFixed(1) + "%"
}

// ---------------------------------------------------------------------------
// Toggle button strip
// ---------------------------------------------------------------------------

const PITCH_GROUP_LABELS: Record<PitchGroup, string> = {
  all: "All",
  fastball: "Fastball",
  breaking: "Breaking",
  offspeed: "Offspeed",
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ZoneHeatmap({
  overlay,
  className = "",
}: {
  overlay: ZoneOverlayData
  className?: string
}) {
  const [group, setGroup] = useState<PitchGroup>("all")
  const [hoveredCell, setHoveredCell] = useState<ZoneCell | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  const groupCells = overlay.cells.filter((c) => c.pitch_group === group)
  const vmax = computeVmax(overlay.cells, group)

  const { sz_top, sz_bot } = overlay.strike_zone
  const { x_edges, z_norm_edges, called_zone } = overlay.grid

  // Strike zone box in SVG coords
  const szX = toSvgX(-called_zone.x_half_ft)
  const szW = toSvgX(called_zone.x_half_ft) - szX
  const szY = toSvgY(called_zone.z_norm[1]) // top (higher z_norm = lower y in SVG)
  const szH = toSvgY(called_zone.z_norm[0]) - szY

  // Max bubble radius proportional to usage
  const maxUsage = Math.max(...groupCells.map((c) => c.pitcher_usage_freq), 0.001)

  const handleCellEnter = useCallback((cell: ZoneCell) => {
    setHoveredCell(cell)
  }, [])

  const handleCellLeave = useCallback(() => {
    setHoveredCell(null)
  }, [])

  const coldStartBatter = overlay.is_cold_start?.batter
  const coldStartPitcher = overlay.is_cold_start?.pitcher
  const anyColdStart = coldStartBatter || coldStartPitcher

  const groups = (overlay.pitch_groups ?? ["all", "fastball", "breaking", "offspeed"]) as PitchGroup[]

  return (
    <div className={`space-y-3 ${className}`}>
      {/* Header row */}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-white">
            {overlay.matchup.batter_name}
            <span className="ml-1.5 text-xs font-normal text-gray-500">
              ({overlay.matchup.b_hand}HB)
            </span>
            <span className="mx-2 text-gray-600">vs</span>
            {overlay.matchup.pitcher_name}
            <span className="ml-1.5 text-xs font-normal text-gray-500">
              ({overlay.matchup.p_hand}HP)
            </span>
          </p>
          <p className="text-[10px] text-gray-600 mt-0.5">
            Profile as of {overlay.as_of_date}
          </p>
        </div>
        {anyColdStart && (
          <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-400 uppercase tracking-wider shrink-0">
            Limited data
            {coldStartBatter && !coldStartPitcher && " · batter"}
            {coldStartPitcher && !coldStartBatter && " · pitcher"}
          </span>
        )}
      </div>

      {/* Pitch group toggle */}
      <div
        role="tablist"
        aria-label="Pitch group filter"
        className="inline-flex rounded-lg border border-[#262626] bg-[#111] p-0.5 gap-0.5"
      >
        {groups.map((g) => (
          <button
            key={g}
            role="tab"
            aria-selected={group === g}
            onClick={() => setGroup(g)}
            className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
              group === g
                ? "bg-[#10b981] text-black"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {PITCH_GROUP_LABELS[g] ?? g}
          </button>
        ))}
      </div>

      {/* SVG + tooltip layout */}
      <div className="flex flex-col sm:flex-row gap-3 items-start">
        {/* SVG heatmap — responsive, max 260px wide */}
        <div
          className="relative w-full max-w-[260px] shrink-0 mx-auto sm:mx-0"
          style={{ aspectRatio: `${SVG_W} / ${SVG_H}` }}
        >
          <svg
            ref={svgRef}
            viewBox={`0 0 ${SVG_W} ${SVG_H}`}
            width="100%"
            height="100%"
            className="block overflow-visible"
            aria-label={`Zone heatmap for ${overlay.matchup.batter_name} vs ${overlay.matchup.pitcher_name}, ${PITCH_GROUP_LABELS[group]} pitches`}
            role="img"
          >
            {/* ── 25 cells ── */}
            {groupCells.map((cell) => {
              const ix = cell.ix
              const iz = cell.iz
              const x1 = toSvgX(x_edges[ix])
              const x2 = toSvgX(x_edges[ix + 1])
              const y1 = toSvgY(z_norm_edges[iz + 1]) // top (higher z = lower y)
              const y2 = toSvgY(z_norm_edges[iz])     // bottom
              const fill = valueToColor(cell.batter_run_value, vmax)
              const isHovered = hoveredCell === cell
              const cellKey = `${ix}-${iz}`

              return (
                <g key={cellKey}>
                  <rect
                    x={x1}
                    y={y1}
                    width={x2 - x1}
                    height={y2 - y1}
                    fill={fill}
                    stroke={isHovered ? "#ffffff" : "#0a0a0a"}
                    strokeWidth={isHovered ? 1.5 : 0.5}
                    onMouseEnter={() => handleCellEnter(cell)}
                    onMouseLeave={handleCellLeave}
                    onFocus={() => handleCellEnter(cell)}
                    onBlur={handleCellLeave}
                    tabIndex={0}
                    role="gridcell"
                    aria-label={`${cell.batter_run_value != null ? fmtRV(cell.batter_run_value) : "no data"}, pitcher ${fmtPct(cell.pitcher_usage_freq)} here`}
                    className="cursor-default focus:outline-none"
                  />
                </g>
              )
            })}

            {/* ── Strike zone box (called_zone) drawn on top of cells ── */}
            <rect
              x={szX}
              y={szY}
              width={szW}
              height={szH}
              fill="none"
              stroke="#e5e7eb"
              strokeWidth={1.5}
              strokeDasharray="none"
              pointerEvents="none"
            />

            {/* ── Pitcher location bubbles ── */}
            {groupCells
              .filter((cell) => cell.pitcher_usage_freq > 0.005)
              .map((cell) => {
                const locZNorm = zFtToNorm(cell.pitcher_loc.z_ft, sz_bot, sz_top)
                const cx = toSvgX(cell.pitcher_loc.x_ft)
                const cy = toSvgY(locZNorm)
                const r = Math.sqrt(cell.pitcher_usage_freq / maxUsage) * 9
                const isHovered = hoveredCell === cell

                return (
                  <circle
                    key={`bubble-${cell.ix}-${cell.iz}`}
                    cx={cx}
                    cy={cy}
                    r={r}
                    fill="rgba(255,255,255,0.55)"
                    stroke={isHovered ? "#ffffff" : "rgba(255,255,255,0.2)"}
                    strokeWidth={isHovered ? 1.5 : 0.5}
                    pointerEvents="none"
                  />
                )
              })}
          </svg>
        </div>

        {/* Info panel: hovered cell detail OR standing instructions */}
        <div className="flex-1 min-w-0">
          {hoveredCell ? (
            <div className="rounded-lg border border-[#262626] bg-[#111] px-4 py-3 space-y-1.5">
              <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest mb-2">
                Cell detail
              </p>
              <div className="flex justify-between text-xs">
                <span className="text-gray-400">Batter run value</span>
                <span className={`font-mono font-semibold ${
                  hoveredCell.batter_run_value == null ? "text-gray-600"
                  : hoveredCell.batter_run_value > 0 ? "text-red-400"
                  : hoveredCell.batter_run_value < 0 ? "text-blue-400"
                  : "text-gray-400"
                }`}>
                  {fmtRV(hoveredCell.batter_run_value)}
                </span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-400">Pitcher throws here</span>
                <span className="font-mono text-gray-300">
                  {fmtPct(hoveredCell.pitcher_usage_freq)}
                </span>
              </div>
              {hoveredCell.batter_whiff != null && (
                <div className="flex justify-between text-xs">
                  <span className="text-gray-400">Batter whiff rate</span>
                  <span className="font-mono text-gray-300">{fmtPct(hoveredCell.batter_whiff)}</span>
                </div>
              )}
              {hoveredCell.batter_xwoba != null && (
                <div className="flex justify-between text-xs">
                  <span className="text-gray-400">Batter xwOBA on contact</span>
                  <span className="font-mono text-gray-300">{hoveredCell.batter_xwoba.toFixed(3)}</span>
                </div>
              )}
              <div className="pt-1 border-t border-[#1e1e1e]">
                <p className="text-[10px] text-gray-600">
                  Zone cell ({hoveredCell.ix === 0 ? "far left" : hoveredCell.ix === 4 ? "far right" : hoveredCell.ix === 2 ? "center" : hoveredCell.ix < 2 ? "left" : "right"},
                  {" "}{hoveredCell.iz === 0 ? "low" : hoveredCell.iz === 4 ? "high" : hoveredCell.iz === 2 ? "middle" : hoveredCell.iz < 2 ? "low-middle" : "high-middle"}) ·
                  {" "}{hoveredCell.x_ft.toFixed(2)} ft × z={hoveredCell.z_norm.toFixed(2)}
                </p>
              </div>
            </div>
          ) : (
            <div className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-4 py-3 space-y-3">
              {/* Legend */}
              <div className="space-y-1.5">
                <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest">Legend</p>
                <div className="flex items-center gap-2">
                  <span className="h-3 w-5 rounded-sm shrink-0" style={{ background: "rgb(239,68,68)" }} />
                  <span className="text-xs text-gray-400">Batter hot zone (positive run value)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="h-3 w-5 rounded-sm shrink-0" style={{ background: "rgb(38,38,38)" }} />
                  <span className="text-xs text-gray-400">Neutral (near zero)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="h-3 w-5 rounded-sm shrink-0" style={{ background: "rgb(59,130,246)" }} />
                  <span className="text-xs text-gray-400">Batter cold zone (negative run value)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="h-3 w-5 rounded-sm shrink-0 flex items-center justify-center">
                    <span className="h-2.5 w-2.5 rounded-full bg-white/50 border border-white/20" />
                  </span>
                  <span className="text-xs text-gray-400">Pitcher location density (bubble = frequency)</span>
                </div>
                <div className="flex items-center gap-2">
                  <svg width="20" height="12" viewBox="0 0 20 12" className="shrink-0">
                    <rect x="1" y="1" width="18" height="10" fill="none" stroke="#e5e7eb" strokeWidth="1.5" />
                  </svg>
                  <span className="text-xs text-gray-400">Rulebook strike zone</span>
                </div>
              </div>
              <p className="text-[10px] text-gray-600 border-t border-[#1e1e1e] pt-2">
                Hover or focus a cell for exact numbers.
              </p>
            </div>
          )}

          {/* Overlap scalar (matchup summary) */}
          {overlay.overlap_scalar != null && (
            <div className="mt-2 rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-4 py-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Matchup overlap</span>
                <span className={`text-xs font-mono font-semibold ${
                  overlay.overlap_scalar > 0 ? "text-red-400" : overlay.overlap_scalar < 0 ? "text-blue-400" : "text-gray-400"
                }`}>
                  {overlay.overlap_scalar >= 0 ? "+" : ""}
                  {overlay.overlap_scalar.toFixed(4)}
                </span>
              </div>
              <p className="text-[10px] text-gray-600 mt-0.5">
                Expected batter run value/pitch, usage-weighted. &gt;0 favors batter.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Caption — honest, non-edge framing */}
      <p className="text-[11px] text-gray-500 leading-relaxed">
        <span className="text-red-400 font-medium">Red</span> = this batter has historically performed better in this zone (positive run value).{" "}
        <span className="text-blue-400 font-medium">Blue</span> = historically worse.{" "}
        <span className="text-white/60 font-medium">Bubbles</span> = where this pitcher actually locates pitches (size = frequency).{" "}
        The white box is the rulebook strike zone (height-adjusted to this batter).{" "}
        <span className="text-gray-600">This is an explanatory transparency view of the matchup — not a bet signal (zone profiles tested null for predictive edge).</span>
      </p>
    </div>
  )
}
