"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Info } from "lucide-react"
import { apiFetch } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"

// ---------------------------------------------------------------------------
// Types — mirrors betting_ml/utils/tb_projection_serving.build_tb_projection_payload
// ---------------------------------------------------------------------------

interface BookComparison {
  book: string
  line: number
  is_integer_line: boolean
  over_odds: number | null
  under_odds: number | null
  book_implied_p_over: number | null
  book_hold: number | null
  model_p_over: number | null
  model_p_under: number | null
  model_p_push: number | null
  model_vs_book_p_over: number | null
  model_mean_minus_line: number | null
}

interface TbDistribution {
  quantile_levels: number[]
  tb_quantile_grid: number[]
  mean: number | null
  median: number | null
  std: number | null
  p05: number | null
  p95: number | null
  p_ge: Record<string, number> | null
}

export interface TbProjection {
  batter_id: number
  full_name: string | null
  team: string | null
  opponent: string | null
  game_pk: number | null
  game_date: string | null
  game_datetime: string | null
  batting_slot: number | null
  model_version: string
  model_fit_date: string | null
  distribution: TbDistribution
  book_comparisons: BookComparison[]
  primary_line: number | null
  caption: string
  disclaimer: string
  calibration_note: string | null
  best_alpha: number
  is_bet_recommendation: boolean
  regular_season_only: boolean
}

// Honest-framing fallback — mirrors betting_ml/utils/tb_projection_serving.DISCLAIMER, shown if a
// payload ever omits its server-written disclaimer so the surface ALWAYS carries it. This is a
// projection + transparency comparison, never a recommendation (best_alpha = 0).
const DISCLAIMER_FALLBACK =
  "Projections reflect our model; they are not betting advice and we make no profitability claim. " +
  "Single-game total-bases outcomes are high-variance — treat this as informational context, not a " +
  "play. The model is fit on regular-season games only."

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtGameTime(raw: string | null): string | null {
  if (!raw) return null
  const iso = raw.endsWith("Z") || /[+-]\d\d:?\d\d$/.test(raw) ? raw : raw + "Z"
  const d = new Date(iso)
  if (isNaN(d.getTime())) return null
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  })
}

function gridAt(dist: TbDistribution, level: number): number | null {
  const i = dist.quantile_levels.findIndex((q) => Math.abs(q - level) < 1e-6)
  return i >= 0 ? dist.tb_quantile_grid[i] : null
}

function fmtOdds(o: number | null): string {
  if (o == null) return "—"
  return o > 0 ? `+${o}` : `${o}`
}

function fmtPct(p: number | null | undefined): string {
  if (p == null) return "—"
  return `${(p * 100).toFixed(0)}%`
}

function fmtSignedPct(p: number | null): string {
  if (p == null) return "—"
  const v = p * 100
  return `${v >= 0 ? "+" : ""}${v.toFixed(0)} pts`
}

// ---------------------------------------------------------------------------
// Distribution range strip (P05–P95 band, IQR band, median tick, book-line marker) —
// identical furniture to the pitcher K panel so the two props tabs read as one surface.
// ---------------------------------------------------------------------------

function RangeStrip({ dist, primaryLine }: { dist: TbDistribution; primaryLine: number | null }) {
  const [hover, setHover] = useState(false)

  const p05 = dist.p05 ?? gridAt(dist, 0.05)
  const p95 = dist.p95 ?? gridAt(dist, 0.95)
  const p25 = gridAt(dist, 0.25)
  const p75 = gridAt(dist, 0.75)
  const p10 = gridAt(dist, 0.1)
  const p90 = gridAt(dist, 0.9)
  const median = dist.median ?? gridAt(dist, 0.5)
  if (p05 == null || p95 == null) return null

  const lo = Math.min(p05, primaryLine ?? p05) - 1
  const hi = Math.max(p95, primaryLine ?? p95) + 1
  const span = Math.max(hi - lo, 1)
  const pos = (v: number) => ((v - lo) / span) * 100

  return (
    <div className="mt-6">
      <div
        className="relative h-12 cursor-help"
        onClick={() => setHover((h) => !h)}
        onPointerEnter={(e) => {
          if (e.pointerType === "mouse") setHover(true)
        }}
        onPointerLeave={(e) => {
          if (e.pointerType === "mouse") setHover(false)
        }}
      >
        <div
          className="absolute top-1/2 h-2 -translate-y-1/2 rounded-full bg-[#1f2937]"
          style={{ left: `${pos(p05)}%`, width: `${pos(p95) - pos(p05)}%` }}
        />
        {p25 != null && p75 != null && (
          <div
            className="absolute top-1/2 h-2 -translate-y-1/2 rounded-full bg-emerald-500/40"
            style={{ left: `${pos(p25)}%`, width: `${pos(p75) - pos(p25)}%` }}
          />
        )}
        {median != null && (
          <div
            className="absolute top-1/2 h-6 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded bg-emerald-400"
            style={{ left: `${pos(median)}%` }}
          />
        )}
        {primaryLine != null && (
          <div
            className="absolute top-1/2 h-8 w-[2px] -translate-x-1/2 -translate-y-1/2 bg-amber-400/90"
            style={{ left: `${pos(primaryLine)}%` }}
            title={`Consensus book line: ${primaryLine}`}
          >
            <span className="absolute -top-5 left-1/2 -translate-x-1/2 whitespace-nowrap text-[10px] font-medium text-amber-400">
              line {primaryLine}
            </span>
          </div>
        )}

        {hover && (
          <div className="pointer-events-none absolute -top-2 left-1/2 z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-lg border border-[#262626] bg-[#0d0d0d] px-3 py-2 text-[11px] shadow-lg">
            <div className="flex items-center gap-2">
              <span className="text-gray-500">Projected median</span>
              <span className="tabular-nums font-semibold text-emerald-400">{median ?? "—"} TB</span>
            </div>
            {p10 != null && p90 != null && (
              <div className="flex items-center gap-2">
                <span className="text-gray-500">80% interval</span>
                <span className="tabular-nums text-white">
                  {p10}–{p90} TB
                </span>
              </div>
            )}
            <div className="flex items-center gap-2">
              <span className="text-gray-500">5th–95th pct</span>
              <span className="tabular-nums text-gray-300">
                {p05}–{p95} TB
              </span>
            </div>
          </div>
        )}
      </div>

      <div className="flex justify-between text-[10px] text-gray-600">
        <span>{p05} TB</span>
        <span className="text-emerald-400/80">middle 50% shaded · median tick · hover/tap for interval</span>
        <span>{p95} TB</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

export function BatterTbProjection({ batterId, asOf }: { batterId: number; asOf?: string | null }) {
  const { accessToken } = useAuth()

  const { data, isError } = useQuery<TbProjection>({
    queryKey: ["tb-projection", batterId, asOf ?? "latest"],
    queryFn: () =>
      apiFetch(`/players/${batterId}/tb-projection${asOf ? `?as_of=${asOf}` : ""}`, {}, accessToken!),
    enabled: !!accessToken,
    staleTime: 1000 * 60 * 30,
    retry: false, // a 404 (no projection for this date) is expected — fail quietly
  })

  if (isError || !data) return null

  const dist = data.distribution
  if (!dist || !dist.tb_quantile_grid?.length) return null

  const gameTime = fmtGameTime(data.game_datetime) ?? data.game_date
  const pGe = dist.p_ge ?? {}

  return (
    <section className="mb-8">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
          Total Bases Projection
        </h2>
        <span className="text-[10px] text-gray-600">
          model: {data.model_version}
          {data.model_fit_date ? ` · fit ${data.model_fit_date}` : ""}
        </span>
      </div>

      {/* Batter identity + matchup context */}
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div>
          <span className="text-lg font-bold text-white">{data.full_name ?? "—"}</span>
          <span className="ml-2 text-xs">
            <span className="font-medium text-gray-200">{data.team ?? "—"}</span>
            {data.opponent ? <span className="text-gray-600"> vs {data.opponent}</span> : null}
          </span>
        </div>
        <div className="flex items-center gap-4 text-[11px] text-gray-500">
          {gameTime && <span>{gameTime}</span>}
          {data.batting_slot != null && <span>Batting {data.batting_slot}</span>}
        </div>
      </div>

      <div className="rounded-lg border border-[#262626] bg-[#111111] px-4 py-4">
        {/* Headline: our number vs the book's line */}
        <div className="flex flex-wrap items-end gap-x-8 gap-y-2">
          <div>
            <span className="block text-[11px] uppercase tracking-wider text-gray-500">
              We project
            </span>
            <span className="text-2xl font-bold tabular-nums text-emerald-400">
              {dist.mean != null ? dist.mean.toFixed(1) : "—"}
              <span className="ml-1 text-sm font-normal text-gray-500">TB</span>
            </span>
          </div>
          {data.primary_line != null && (
            <div>
              <span className="block text-[11px] uppercase tracking-wider text-gray-500">
                Book line
              </span>
              <span className="text-2xl font-bold tabular-nums text-amber-400">
                {data.primary_line}
                <span className="ml-1 text-sm font-normal text-gray-500">TB</span>
              </span>
            </div>
          )}
          {data.primary_line != null && dist.mean != null && (
            <div>
              <span className="block text-[11px] uppercase tracking-wider text-gray-500">
                Difference
              </span>
              <span className="text-2xl font-bold tabular-nums text-white">
                {dist.mean - data.primary_line >= 0 ? "+" : ""}
                {(dist.mean - data.primary_line).toFixed(1)}
                <span className="ml-1 text-sm font-normal text-gray-500">TB</span>
              </span>
            </div>
          )}
        </div>

        {/* P(TB ≥ k) chips — the calibration surface's headline read */}
        <div className="mt-4 flex flex-wrap gap-2">
          {["1", "2", "3", "4"].map((k) =>
            pGe[k] != null ? (
              <div
                key={k}
                className="rounded-md border border-[#262626] bg-[#0d0d0d] px-2.5 py-1.5 text-center"
              >
                <div className="text-[10px] uppercase tracking-wider text-gray-600">{k}+ bases</div>
                <div className="text-sm font-semibold tabular-nums text-gray-200">{fmtPct(pGe[k])}</div>
              </div>
            ) : null,
          )}
        </div>

        <RangeStrip dist={dist} primaryLine={data.primary_line} />

        {/* Per-book transparency comparison */}
        {data.book_comparisons.length > 0 && (
          <div className="mt-5 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#262626] text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                  <th className="px-2 py-2 text-left">Book</th>
                  <th className="px-2 py-2 text-right">Line</th>
                  <th className="px-2 py-2 text-right">Over / Under</th>
                  <th className="hidden px-2 py-2 text-right sm:table-cell">Book Over%*</th>
                  <th className="px-2 py-2 text-right">Our Over%</th>
                  <th className="hidden px-2 py-2 text-right sm:table-cell">Push%</th>
                  <th className="px-2 py-2 text-right">Model − Book</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1a1a1a]">
                {data.book_comparisons.map((c, i) => (
                  <tr key={`${c.book}-${i}`} className="text-white">
                    <td className="px-2 py-2 font-medium capitalize">{c.book}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{c.line}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-gray-400">
                      {fmtOdds(c.over_odds)} / {fmtOdds(c.under_odds)}
                    </td>
                    <td className="hidden px-2 py-2 text-right tabular-nums text-gray-400 sm:table-cell">
                      {fmtPct(c.book_implied_p_over)}
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums text-emerald-400">
                      {fmtPct(c.model_p_over)}
                    </td>
                    <td className="hidden px-2 py-2 text-right tabular-nums text-gray-500 sm:table-cell">
                      {c.is_integer_line ? fmtPct(c.model_p_push) : "—"}
                    </td>
                    <td
                      className={`px-2 py-2 text-right tabular-nums ${
                        (c.model_vs_book_p_over ?? 0) >= 0 ? "text-emerald-400" : "text-gray-400"
                      }`}
                    >
                      {fmtSignedPct(c.model_vs_book_p_over)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-1.5 text-[10px] text-gray-600">
              *Book Over% is the sportsbook&apos;s price with its margin removed (de-vigged), so books
              are comparable. On a whole-number line, Push% is our probability the result lands
              exactly on it (a push refunds the stake). &quot;Model − Book&quot; is the gap between our
              projection and that price — a transparency comparison, not a recommendation.
            </p>
          </div>
        )}

        {/* Calibration methodology note (server-written; the strongest allowed claim) */}
        {data.calibration_note && (
          <p className="mt-4 text-[11px] leading-relaxed text-gray-500">{data.calibration_note}</p>
        )}

        {/* Honest-framing disclaimer (written server-side; mirrored here as the on-page caption) */}
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2.5">
          <Info className="mt-0.5 h-3 w-3 shrink-0 text-gray-600" />
          <p className="text-[11px] leading-relaxed text-gray-500">
            {data.disclaimer || DISCLAIMER_FALLBACK}
          </p>
        </div>
      </div>
    </section>
  )
}
