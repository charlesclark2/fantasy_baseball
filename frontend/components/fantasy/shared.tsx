"use client"

// Shared presentation pieces for the NFL fantasy surfaces (NF3). Position colours, the format
// selector, and the honest-uncertainty primitives live here so all four surfaces (Projections,
// Rankings, League Board, Draft Optimizer) read as one product.
//
// 🚨 CLAIM SCOPE (NF-D3): these surfaces are a PROJECTION product. They never claim to beat a
// consensus, an ADP, or any competitor — the honest framing is uncertainty made visible (an 80%
// range on every number) plus transparency about how the number is built. Copy here is the one
// place that framing is written down; keep new copy inside it.

import { Info } from "lucide-react"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
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

/** A column header (or any label) with an explainer on hover/focus. These boards use several terms
 *  of art — VOR, replacement, ADP — that are unreadable at a glance to anyone who has not met them,
 *  so the definition travels with the column rather than living in a paragraph below the table. */
export function InfoTip({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex cursor-help items-center gap-1 underline decoration-dotted decoration-gray-600 underline-offset-4">
          {label}
          <Info className="h-3 w-3 text-gray-600" aria-hidden />
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-xs leading-relaxed">{children}</TooltipContent>
    </Tooltip>
  )
}

/** Definitions shared by the boards — one wording, so a term never means two things across surfaces. */
export const GLOSSARY = {
  vor: "Value over replacement. A player's projected points minus the points of the best player at his position who does NOT start anywhere in your league. It is what makes positions comparable: an elite quarterback scores more raw points than an elite running back, but if every team can start a good quarterback anyway, those points buy you less.",
  replacement:
    "The points of the first player at this position who does not crack a starting lineup anywhere in the league — the level you could get for free off waivers. It moves with your format: more teams, or a superflex spot, pushes it deeper.",
  nextAtPos:
    "How much value you give up by passing on this player and taking the next one at his position instead. A big number means a cliff — the tier ends here. A small number means you can comfortably wait.",
  adp: "Average draft position across thousands of real public drafts (Fantasy Football Calculator), matched to your scoring format and league size. It is a picture of what other drafters are doing — a reference point, not a target and not a competitor we claim to beat.",
  adpDelta:
    "Where our board differs from the room: ADP minus our rank. Positive means the public typically drafts him later than we rank him; negative means they take him earlier. Big gaps are where our projection and the consensus genuinely disagree — read them alongside the 80% range, which tells you how sure the model is.",
} as const

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

/** ADP delta, signed and coloured. Emerald = we rank him higher than the room drafts him. The colour
 *  is a "we differ here" cue, NOT a value/edge claim — the tooltip on the column says so. */
export function AdpDelta({ delta }: { delta: number | null }) {
  if (delta == null) return <span className="text-gray-600">—</span>
  const rounded = Math.round(delta)
  if (rounded === 0) return <span className="text-gray-500">0</span>
  return (
    <span className={rounded > 0 ? "text-emerald-400" : "text-rose-400"}>
      {rounded > 0 ? `+${rounded}` : rounded}
    </span>
  )
}

export const PAGE_SIZES = [25, 50, 100] as const
export const ALL_ROWS = -1

/** Page-size picker + pager. `total` is the filtered row count, so the caller can page a view that
 *  is already sorted/filtered without this component knowing anything about the data. */
export function Pagination({
  page,
  pageSize,
  total,
  onPage,
  onPageSize,
}: {
  page: number
  pageSize: number
  total: number
  onPage: (p: number) => void
  onPageSize: (n: number) => void
}) {
  const showingAll = pageSize === ALL_ROWS
  const pages = showingAll ? 1 : Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : showingAll ? 1 : page * pageSize + 1
  const to = showingAll ? total : Math.min(total, (page + 1) * pageSize)
  const btn =
    "rounded border border-[#262626] bg-[#0f0f0f] px-2 py-1 text-xs text-gray-400 transition-colors hover:text-gray-200 disabled:cursor-not-allowed disabled:opacity-40"
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500">
      <label className="flex items-center gap-1.5">
        <span>Show</span>
        <select
          value={pageSize}
          onChange={(e) => {
            onPageSize(Number(e.target.value))
            onPage(0)
          }}
          className="rounded border border-[#262626] bg-[#0f0f0f] px-2 py-1 text-xs text-gray-200 focus:border-[#10b981] focus:outline-none"
        >
          {PAGE_SIZES.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
          <option value={ALL_ROWS}>All</option>
        </select>
      </label>
      <span>
        {from.toLocaleString()}–{to.toLocaleString()} of {total.toLocaleString()}
      </span>
      {!showingAll && pages > 1 && (
        <div className="flex items-center gap-1.5">
          <button className={btn} onClick={() => onPage(0)} disabled={page === 0}>
            «
          </button>
          <button className={btn} onClick={() => onPage(page - 1)} disabled={page === 0}>
            Prev
          </button>
          <span className="px-1">
            Page {page + 1} of {pages}
          </span>
          <button className={btn} onClick={() => onPage(page + 1)} disabled={page >= pages - 1}>
            Next
          </button>
          <button className={btn} onClick={() => onPage(pages - 1)} disabled={page >= pages - 1}>
            »
          </button>
        </div>
      )}
    </div>
  )
}

/** Download rows as CSV. Exports the WHOLE filtered set, not just the visible page — a paginated
 *  export would silently hand back 50 of 700 rows. */
export function downloadCsv(filename: string, headers: string[], rows: (string | number | null)[][]) {
  const esc = (v: string | number | null) => {
    if (v == null) return ""
    const s = String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const csv = [headers.map(esc).join(","), ...rows.map((r) => r.map(esc).join(","))].join("\n")
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8;" }))
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
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
