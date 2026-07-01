"use client"

import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { Info } from "lucide-react"
import { Nav } from "@/components/nav"
import { AuthGuard } from "@/components/auth-guard"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/lib/auth-context"
import { apiFetch } from "@/lib/api"

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

function fmtPct(p: number | null): string {
  if (p == null) return "—"
  return `${(p * 100).toFixed(0)}%`
}

function fmtSignedPct(p: number | null): string {
  if (p == null) return "—"
  const v = p * 100
  return `${v >= 0 ? "+" : ""}${v.toFixed(0)} pts`
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
      href={`/players/${r.pitcher_id}`}
      className="block rounded-lg border border-[#262626] bg-[#111111] p-4 transition-colors hover:border-[#3a3a3a] hover:bg-[#141414]"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-semibold text-white">{r.full_name ?? `Pitcher ${r.pitcher_id}`}</div>
          <div className="truncate text-[11px] text-gray-500">
            {r.team ?? "—"}
            {r.opponent ? <span className="text-gray-600"> vs {r.opponent}</span> : null}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-wider text-gray-500">Proj K</div>
          <div className="text-2xl font-bold tabular-nums text-emerald-400">
            {r.mean != null ? r.mean.toFixed(1) : "—"}
          </div>
        </div>
      </div>

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

function ProjectionsPageInner() {
  const { accessToken, email } = useAuth()

  const { data, isLoading, isError } = useQuery<ProjectionIndex>({
    queryKey: ["k-projections-today"],
    queryFn: () => apiFetch("/players/k-projections/today", {}, accessToken!),
    enabled: !!accessToken,
    staleTime: 1000 * 60 * 30,
  })

  const pitchers = data?.pitchers ?? []

  return (
    <>
      <Nav authenticated activeLink="projections" userEmail={email} />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <div className="mb-2 flex items-baseline justify-between">
          <h1 className="text-2xl font-bold text-white">Strikeout Projections</h1>
          {data?.game_date && (
            <span className="text-xs text-gray-500">{data.game_date}</span>
          )}
        </div>
        <p className="mb-5 max-w-3xl text-sm text-gray-500">
          Our model&apos;s projected strikeout total for each probable starter, shown next to the
          sportsbooks&apos; posted line. Projections and a transparency comparison only — click a
          pitcher for the full distribution and per-book breakdown.
        </p>

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
            <p className="text-sm text-gray-400">No projections posted yet.</p>
            <p className="mt-1 text-xs text-gray-600">
              Projections appear once probable starters are announced for the day&apos;s slate.
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

export default function ProjectionsPage() {
  return (
    <AuthGuard>
      <ProjectionsPageInner />
    </AuthGuard>
  )
}
