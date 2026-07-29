"use client"

// Shared presentation pieces for the NFL fantasy surfaces (NF3). Position colours, the format
// selector, and the honest-uncertainty primitives live here so all four surfaces (Projections,
// Rankings, League Board, Draft Optimizer) read as one product.
//
// 🚨 CLAIM SCOPE (NF-D3): these surfaces are a PROJECTION product. They never claim to beat a
// consensus, an ADP, or any competitor — the honest framing is uncertainty made visible (an 80%
// range on every number) plus transparency about how the number is built. Copy here is the one
// place that framing is written down; keep new copy inside it.

import type { LeagueConfigMeta, Manifest } from "@/lib/draft-optimizer"

export const POS_COLORS: Record<string, string> = {
  QB: "text-rose-400 bg-rose-500/10 border-rose-500/30",
  RB: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  WR: "text-sky-400 bg-sky-500/10 border-sky-500/30",
  TE: "text-amber-400 bg-amber-500/10 border-amber-500/30",
  K: "text-violet-400 bg-violet-500/10 border-violet-500/30",
  DST: "text-teal-400 bg-teal-500/10 border-teal-500/30",
}

export const SKILL_POSITIONS = ["QB", "RB", "WR", "TE"] as const

/** A player's team for display: real abbreviation, or an honest label for the unteamed. A rookie's
 *  NFL team is not always resolved upstream, so an unteamed rookie shows "Rk", never a wrong "FA". */
export const teamLabel = (p: { team: string | null; rookie: boolean }) =>
  p.team ?? (p.rookie ? "Rk" : "FA")

export const num = (v: number | null | undefined, nd = 1) =>
  v == null ? "—" : v.toLocaleString(undefined, { minimumFractionDigits: nd, maximumFractionDigits: nd })

export const int = (v: number | null | undefined) => (v == null ? "—" : Math.round(v).toLocaleString())

export function PosBadge({ pos }: { pos: string }) {
  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 text-[10px] font-semibold ${
        POS_COLORS[pos] ?? "text-gray-400 bg-gray-500/10 border-gray-500/30"
      }`}
    >
      {pos}
    </span>
  )
}

const CONF_STYLE: Record<string, string> = {
  high: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  medium: "text-amber-400 bg-amber-500/10 border-amber-500/30",
  low: "text-gray-400 bg-gray-500/10 border-gray-500/30",
}

/** The model's own confidence tier — driven by how much history backs the player's per-game line. */
export function ConfidenceBadge({ conf }: { conf: string | null }) {
  if (!conf) return <span className="text-gray-600">—</span>
  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 text-[10px] font-medium capitalize ${
        CONF_STYLE[conf] ?? CONF_STYLE.low
      }`}
    >
      {conf}
    </span>
  )
}

export function RookieBadge() {
  return (
    <span className="inline-block rounded border border-indigo-500/30 bg-indigo-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-300">
      R
    </span>
  )
}

/** How a row's interval was produced — the honest caveat, not a decoration. */
export const UNCERTAINTY_LABEL: Record<string, string> = {
  empirical: "Empirical",
  calibrated: "Calibrated",
}
export const UNCERTAINTY_HELP: Record<string, string> = {
  empirical:
    "Empirical — the range comes from this player's own game-to-game scoring variance across his played history.",
  calibrated:
    "Calibrated — a rookie has no NFL history, so the range comes from how rookies at this draft slot have actually landed. Wider on purpose.",
}

/** A p10–p90 band drawn on a shared domain, with the projection marked. The visual carries the
 *  uncertainty that a single number hides — the point is deliberately a small tick, not a bar. */
export function IntervalBar({
  p10,
  point,
  p90,
  min,
  max,
}: {
  p10: number | null | undefined
  point: number | null | undefined
  p90: number | null | undefined
  min: number
  max: number
}) {
  const span = max - min
  if (span <= 0 || p10 == null || p90 == null) return <div className="h-1.5" />
  const pct = (v: number) => Math.min(100, Math.max(0, ((v - min) / span) * 100))
  const left = pct(p10)
  const right = pct(p90)
  return (
    <div className="relative h-1.5 w-full rounded-full bg-[#1a1a1a]">
      <div
        className="absolute h-1.5 rounded-full bg-emerald-500/30"
        style={{ left: `${left}%`, width: `${Math.max(right - left, 0.5)}%` }}
      />
      {point != null && (
        <div
          className="absolute top-[-2px] h-[10px] w-[2px] rounded-sm bg-emerald-400"
          style={{ left: `${pct(point)}%` }}
        />
      )}
    </div>
  )
}

/** The standing honest-uncertainty explainer every browse surface carries. */
export function UncertaintyNote({ children }: { children?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-4 text-xs leading-relaxed text-gray-400">
      <p>
        <span className="font-semibold text-gray-300">Every number here is a range, not a call.</span>{" "}
        The projection is the middle of a distribution; the 80% range is where the model puts roughly
        eight of ten seasons for that player. A wide range is the model telling you it does not know —
        read the range before the point.
      </p>
      {children}
      <p className="mt-2">
        This is a projection and transparency tool for your own draft decisions. It is a current model
        and modelling is ongoing; we make no claim that it beats any particular ranking, and nothing
        here is betting advice.
      </p>
    </div>
  )
}

/** Provenance strip — what the numbers were built from and when. */
export function ProvenanceLine({
  season,
  generatedAt,
  extra,
}: {
  season: number
  generatedAt?: string | null
  extra?: string | null
}) {
  const when = generatedAt ? new Date(generatedAt) : null
  return (
    <p className="text-[11px] text-gray-600">
      {season} season projections
      {extra ? ` · ${extra}` : ""}
      {when && !isNaN(when.getTime()) ? ` · built ${when.toLocaleDateString()}` : ""}
    </p>
  )
}

export function SurfaceHeader({
  title,
  blurb,
  children,
}: {
  title: string
  blurb: string
  children?: React.ReactNode
}) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-semibold text-white">{title}</h1>
      <p className="mt-1 max-w-3xl text-sm text-gray-400">{blurb}</p>
      {children}
    </div>
  )
}

const selectClass =
  "rounded border border-[#262626] bg-[#0f0f0f] px-2.5 py-1.5 text-sm text-gray-200 focus:border-[#10b981] focus:outline-none"

/** League format + size picker. Manifest-driven: whatever (config, size) combos were exported are
 *  exactly what is offered, so a preset that has not been built never renders as a dead option. */
export function FormatSelector({
  manifest,
  configName,
  size,
  onConfig,
  onSize,
}: {
  manifest: Manifest | undefined
  configName: string | null
  size: number | null
  onConfig: (c: string) => void
  onSize: (n: number) => void
}) {
  if (!manifest) return null
  const config: LeagueConfigMeta | undefined = manifest.configs.find((c) => c.name === configName)
  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1">
        <span className="text-[11px] uppercase tracking-wider text-gray-500">Scoring format</span>
        <select
          className={selectClass}
          value={configName ?? ""}
          onChange={(e) => onConfig(e.target.value)}
        >
          {manifest.configs.map((c) => (
            <option key={c.name} value={c.name}>
              {c.label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-[11px] uppercase tracking-wider text-gray-500">League size</span>
        <select
          className={selectClass}
          value={size ?? ""}
          onChange={(e) => onSize(Number(e.target.value))}
        >
          {manifest.sizes.map((n) => (
            <option key={n} value={n}>
              {n} teams
            </option>
          ))}
        </select>
      </label>
      {config && (
        <p className="max-w-md pb-1.5 text-[11px] leading-relaxed text-gray-500">
          {config.description}
        </p>
      )}
    </div>
  )
}

/** Position filter chips. */
export function PositionTabs({
  value,
  onChange,
  positions = [...SKILL_POSITIONS],
  allLabel = "All",
}: {
  value: string
  onChange: (p: string) => void
  positions?: string[]
  allLabel?: string
}) {
  const opts = [allLabel, ...positions]
  return (
    <div className="flex flex-wrap gap-1.5">
      {opts.map((p) => (
        <button
          key={p}
          onClick={() => onChange(p)}
          className={`rounded border px-2.5 py-1 text-xs font-medium transition-colors ${
            value === p
              ? "border-[#10b981]/50 bg-[#10b981]/10 text-[#10b981]"
              : "border-[#262626] bg-[#0f0f0f] text-gray-400 hover:text-gray-200"
          }`}
        >
          {p}
        </button>
      ))}
    </div>
  )
}

export function LoadingBlock({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-8 text-center text-sm text-gray-500">
      {label}
    </div>
  )
}

/** The honest empty/failed state — says what is missing rather than showing a blank table. */
export function EmptyBlock({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-8 text-center">
      <p className="text-sm font-medium text-gray-300">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-gray-500">{detail}</p>
    </div>
  )
}
