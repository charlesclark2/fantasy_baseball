"use client"

import { useState } from "react"
import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { format } from "date-fns"
import { CalendarIcon, Info } from "lucide-react"
import { Nav } from "@/components/nav"
import { AuthGuard } from "@/components/auth-guard"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { useAuth } from "@/lib/auth-context"
import { useSelectedDate } from "@/lib/date-context"
import { apiFetch } from "@/lib/api"
import { LogPastPropDialog } from "@/components/log-past-prop-dialog"

// ---------------------------------------------------------------------------
// Prop types — extensible. Only Strikeouts (K) has a projection surface today; add more here as
// their models ship (each maps to its own index endpoint via `endpoint`).
// ---------------------------------------------------------------------------

type PropType = {
  key: string
  label: string
  endpoint: string
  available: boolean
}

const PROP_TYPES: PropType[] = [
  { key: "strikeouts", label: "Strikeouts (K)", endpoint: "/players/k-projections", available: true },
]

// ---------------------------------------------------------------------------
// Types — mirrors betting_ml/utils/k_projection_serving.build_index_payload / index_row
// ---------------------------------------------------------------------------

interface ProjectionRow {
  pitcher_id: number
  full_name: string | null
  team: string | null
  opponent: string | null
  game_pk: number | null
  game_date: string | null
  game_datetime: string | null
  last3_k: number[] | null
  mean: number | null
  median: number | null
  p10: number | null
  p90: number | null
  p05: number | null
  p95: number | null
  primary_line: number | null
  book_count: number
  model_p_over: number | null
  model_vs_book_p_over: number | null
  model_mean_minus_line: number | null
}

interface ProjectionIndex {
  game_date: string | null
  count: number
  pitchers: ProjectionRow[]
  disclaimer?: string
  best_alpha?: number
  is_bet_recommendation?: boolean
}

const DISCLAIMER_FALLBACK =
  "Projections reflect our model; they are not betting advice and we make no profitability claim. " +
  "Single-game strikeout totals are high-variance — treat this as informational context, not a play."

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtSignedPct(p: number | null): string {
  if (p == null) return "—"
  const v = p * 100
  return `${v >= 0 ? "+" : ""}${v.toFixed(0)} pts`
}

// First-pitch time from an ISO timestamp, in the viewer's local zone (e.g. "7:05 PM").
// Mirror the tracker page's parser: use the string as-is if it already carries tz info
// (Z or ±HH:MM); otherwise treat it as UTC by appending "Z" (game_datetime is a UTC instant).
function fmtGameTime(raw: string | null): string | null {
  if (!raw) return null
  const iso = raw.endsWith("Z") || /[+-]\d\d:?\d\d$/.test(raw) ? raw : raw + "Z"
  const d = new Date(iso)
  if (isNaN(d.getTime())) return null
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
}

// Compact range bar: 5th–95th band, 80% (p10–p90) emphasis, median tick, book-line marker.
function MiniRange({ r }: { r: ProjectionRow }) {
  const p05 = r.p05
  const p95 = r.p95
  if (p05 == null || p95 == null) return null
  const line = r.primary_line
  const lo = Math.min(p05, line ?? p05) - 1
  const hi = Math.max(p95, line ?? p95) + 1
  const span = Math.max(hi - lo, 1)
  const pos = (v: number) => ((v - lo) / span) * 100

  return (
    <div className="relative mt-3 h-6">
      <div
        className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-[#1f2937]"
        style={{ left: `${pos(p05)}%`, width: `${pos(p95) - pos(p05)}%` }}
      />
      {r.p10 != null && r.p90 != null && (
        <div
          className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-emerald-500/40"
          style={{ left: `${pos(r.p10)}%`, width: `${pos(r.p90) - pos(r.p10)}%` }}
        />
      )}
      {r.median != null && (
        <div
          className="absolute top-1/2 h-4 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded bg-emerald-400"
          style={{ left: `${pos(r.median)}%` }}
          title={`Projected median: ${r.median} K`}
        />
      )}
      {line != null && (
        <div
          className="absolute top-1/2 h-5 w-[2px] -translate-x-1/2 -translate-y-1/2 bg-amber-400/90"
          style={{ left: `${pos(line)}%` }}
          title={`Book line: ${line}`}
        />
      )}
    </div>
  )
}

function ProjectionCard({ r }: { r: ProjectionRow }) {
  return (
    <Link
      href={r.game_date ? `/props/${r.pitcher_id}?as_of=${r.game_date}` : `/props/${r.pitcher_id}`}
      className="block rounded-lg border border-[#262626] bg-[#111111] p-4 transition-colors hover:border-[#3a3a3a] hover:bg-[#141414]"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-semibold text-white">{r.full_name ?? `Pitcher ${r.pitcher_id}`}</div>
          <div className="truncate text-[11px]">
            <span className="font-medium text-gray-200">{r.team ?? "—"}</span>
            {r.opponent ? <span className="text-gray-600"> vs {r.opponent}</span> : null}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-wider text-gray-500">Proj K</div>
          <div className="text-2xl font-bold tabular-nums text-emerald-400">
            {r.mean != null ? r.mean.toFixed(1) : "—"}
          </div>
          {fmtGameTime(r.game_datetime) && (
            <div className="text-[10px] text-gray-500">{fmtGameTime(r.game_datetime)}</div>
          )}
        </div>
      </div>

      {r.last3_k && r.last3_k.length > 0 && (
        <div className="mt-2 flex items-center gap-1.5 text-[10px] text-gray-500">
          <span className="uppercase tracking-wider text-gray-600">Last 3 K</span>
          {r.last3_k.map((k, i) => (
            <span key={i} className="rounded bg-[#1a1a1a] px-1.5 py-0.5 tabular-nums text-gray-300">
              {k}
            </span>
          ))}
        </div>
      )}

      <MiniRange r={r} />

      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-600">80% range</div>
          <div className="text-xs tabular-nums text-gray-300">
            {r.p10 != null && r.p90 != null ? `${r.p10}–${r.p90}` : "—"}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-600">Book line</div>
          <div className="text-xs tabular-nums text-amber-400">
            {r.primary_line != null ? r.primary_line : "—"}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-600">Model − Book</div>
          <div
            className={`text-xs tabular-nums ${
              (r.model_vs_book_p_over ?? 0) >= 0 ? "text-emerald-400" : "text-gray-400"
            }`}
          >
            {r.model_vs_book_p_over != null ? fmtSignedPct(r.model_vs_book_p_over) : "—"}
          </div>
        </div>
      </div>
    </Link>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function PropsPageInner() {
  const { accessToken, email } = useAuth()
  // Shared slate date — held in the same context as the other betting pages, so the selected day
  // carries across pages.
  const { selectedDate, setSelectedDate, isoDate } = useSelectedDate()
  const [propType, setPropType] = useState<string>(PROP_TYPES[0].key)
  const [calOpen, setCalOpen] = useState(false)

  const active = PROP_TYPES.find((p) => p.key === propType) ?? PROP_TYPES[0]

  const { data, isLoading, isError } = useQuery<ProjectionIndex>({
    queryKey: ["props-index", active.key, isoDate],
    queryFn: () => apiFetch(`${active.endpoint}?as_of=${isoDate}`, {}, accessToken!),
    enabled: !!accessToken && active.available,
    staleTime: 1000 * 60 * 30,
  })

  const pitchers = data?.pitchers ?? []

  return (
    <>
      <Nav authenticated activeLink="props" userEmail={email} />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <h1 className="mb-1 text-2xl font-bold text-white">Props</h1>
        <p className="mb-5 max-w-3xl text-sm text-gray-500">
          Our model&apos;s projection for each probable starter, shown next to the sportsbooks&apos;
          posted line. Projections and a transparency comparison only — click a pitcher for the full
          distribution and per-book breakdown.
        </p>

        {/* Prop-type + date controls */}
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <div className="inline-flex rounded-md border border-[#262626] bg-[#111111] p-0.5">
              {PROP_TYPES.map((p) => (
                <button
                  key={p.key}
                  onClick={() => p.available && setPropType(p.key)}
                  disabled={!p.available}
                  className={`rounded px-3 py-1.5 text-sm font-medium transition-colors ${
                    p.key === propType
                      ? "bg-[#1a1a1a] text-white"
                      : p.available
                        ? "text-gray-500 hover:text-gray-300"
                        : "cursor-not-allowed text-gray-700"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <span className="hidden text-[11px] text-gray-600 sm:inline">More prop types coming soon</span>
          </div>

          <div className="flex items-center gap-2">
          {/* Log a strikeout prop you placed (any game in the last ~14 days) straight into your Bet Log —
              a bookkeeping convenience, works even for past dates with no projection here. */}
          <LogPastPropDialog initialDate={selectedDate} />

          {/* Date picker — the same shared control the other betting pages use */}
          <Popover open={calOpen} onOpenChange={setCalOpen}>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                className="h-9 w-[156px] justify-start gap-2 border-[#262626] bg-[#141414] text-left text-sm font-normal text-white hover:bg-[#1a1a1a]"
              >
                <CalendarIcon className="h-4 w-4 text-gray-500" />
                {format(selectedDate, "MMM d, yyyy")}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto border-[#262626] bg-[#141414] p-0" align="end">
              <Calendar
                mode="single"
                selected={selectedDate}
                onSelect={(d) => {
                  if (d) {
                    setSelectedDate(d)
                    setCalOpen(false)
                  }
                }}
                toDate={new Date()}
                initialFocus
              />
            </PopoverContent>
          </Popover>
          </div>
        </div>

        {isLoading ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-40 w-full rounded-lg" />
            ))}
          </div>
        ) : isError ? (
          <div className="rounded-lg border border-[#262626] bg-[#111111] px-4 py-8 text-center text-sm text-gray-500">
            Couldn&apos;t load projections right now. Please try again shortly.
          </div>
        ) : pitchers.length === 0 ? (
          <div className="rounded-lg border border-[#262626] bg-[#111111] px-4 py-10 text-center">
            <p className="text-sm text-gray-400">
              No projections for {format(selectedDate, "MMM d, yyyy")} yet.
            </p>
            <p className="mt-1 text-xs text-gray-600">
              Projections appear once probable starters are announced for the day&apos;s slate. Try
              another date. To record a prop you placed on a past game, use &quot;Log a prop&quot; above.
            </p>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {pitchers.map((r) => (
              <ProjectionCard key={r.pitcher_id} r={r} />
            ))}
          </div>
        )}

        {/* Honest-framing disclaimer */}
        <div className="mt-6 flex items-start gap-2 rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2.5">
          <Info className="mt-0.5 h-3 w-3 shrink-0 text-gray-600" />
          <p className="text-[11px] leading-relaxed text-gray-500">
            {data?.disclaimer || DISCLAIMER_FALLBACK}
          </p>
        </div>
      </main>
    </>
  )
}

export default function PropsPage() {
  return (
    <AuthGuard>
      <PropsPageInner />
    </AuthGuard>
  )
}
