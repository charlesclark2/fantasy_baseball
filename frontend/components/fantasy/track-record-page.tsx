"use client"

// NF3.2 — the fantasy football past-season TRACK RECORD ("receipts"): our projection vs that
// season's preseason ADP vs the realized outcome, one row per player, per season 2019–2025.
//
// 🔓 PUBLIC BY DESIGN — no FantasyGuard, no entitlement check anywhere in this component. It fetches
// only `lib/fantasy-track-record.ts`'s public endpoints, which structurally can never carry the
// current/locked season (see `export_track_record_json.LOCKED_SEASON`). The 2026 section below is a
// static locked CTA card, never a fetch of real 2026 data that gets hidden — see the module docstring
// on `fantasy_public.py` for why that distinction is the whole point.
//
// 🔒 HONEST (NF-D3 / best_alpha=0): the headline banner renders the manifest's `headline` VERBATIM —
// it is built entirely from the freshly-regenerated NF-D3 scorecard's own numbers at export time
// (`export_track_record_json.build_headline`), never authored here. Do not add new superiority copy
// to this file; if the claim needs to change, it changes at the export.

import { useMemo, useState } from "react"
import Link from "next/link"
import { Lock } from "lucide-react"
import {
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { useAuth } from "@/lib/auth-context"
import { canAccess } from "@/lib/entitlements"
import { useTrackRecordManifest, useTrackRecordSeason } from "@/lib/fantasy-track-record"
import type { TrackRecordRow } from "@/lib/fantasy-track-record"
import {
  EmptyBlock,
  FadeBadge,
  GLOSSARY,
  InfoTip,
  LoadingBlock,
  Pagination,
  PosBadge,
  PositionTabs,
  SurfaceHeader,
  num,
  ALL_ROWS,
  PAGE_SIZES,
  SKILL_POSITIONS,
} from "@/components/fantasy/shared"

function HeadlineBanner({ headline }: { headline: string }) {
  return (
    <div className="mb-6 rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
      <h2 className="mb-1 text-xs font-semibold uppercase tracking-wider text-gray-500">
        The honest read
      </h2>
      <p className="text-sm leading-relaxed text-gray-300">{headline}</p>
    </div>
  )
}

function LockedCurrentSeasonCard({ lockedSeason }: { lockedSeason: number }) {
  const { groups } = useAuth()
  const entitled = canAccess("fantasy", groups)
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#262626] bg-[#111111] p-4">
      <div>
        <p className="text-sm font-medium text-gray-200">
          {lockedSeason} season projections{entitled ? "" : " — subscriber only"}
        </p>
        <p className="mt-1 max-w-md text-xs leading-relaxed text-gray-500">
          This page is the receipts: past seasons, graded against what actually happened. The current
          season&apos;s live projections are the paid product.
        </p>
      </div>
      {entitled ? (
        <Link
          href="/fantasy/projections"
          className="rounded border border-[#10b981]/40 bg-[#10b981]/10 px-3 py-1.5 text-xs font-semibold text-[#10b981] transition-colors hover:bg-[#10b981]/20"
        >
          See {lockedSeason} projections
        </Link>
      ) : (
        <Link
          href="/subscribe"
          className="flex items-center gap-1.5 rounded border border-[#10b981]/40 bg-[#10b981]/10 px-3 py-1.5 text-xs font-semibold text-[#10b981] transition-colors hover:bg-[#10b981]/20"
        >
          <Lock className="h-3 w-3" /> Unlock {lockedSeason}
        </Link>
      )}
    </div>
  )
}

/** Emerald = fade hit, rose = fade miss, amber = fade push, muted gray = not a fade at all — "wins
 *  and losses both" applies to the chart too, not just the table's badge. */
function fadeDotColor(row: TrackRecordRow): string {
  if (!row.isFade) return "#4b5563"
  if (row.fadeResult === "hit") return "#10b981"
  if (row.fadeResult === "miss") return "#f43f5e"
  return "#f59e0b"
}

function FadeDot({ cx, cy, payload }: any) {
  const row = payload as TrackRecordRow
  return (
    <g>
      {/* Invisible larger hit-area — a real finger touch point is ~40-48px, and the visible dot
          below (r=2.5-4) is far smaller than that, so a tap on a real phone was landing between
          dots more often than on one. This circle is unstyled/transparent but still receives
          pointer events by default in SVG (no `pointer-events: none` here), so it enlarges the
          effective tap target without changing what's drawn. */}
      <circle cx={cx} cy={cy} r={14} fill="transparent" />
      <circle
        cx={cx}
        cy={cy}
        r={row.isFade ? 4 : 2.5}
        fill={fadeDotColor(row)}
        fillOpacity={row.isFade ? 0.85 : 0.4}
      />
    </g>
  )
}

function RankScatter({ rows }: { rows: TrackRecordRow[] }) {
  const maxRank = Math.max(1, ...rows.map((r) => Math.max(r.ourRank, r.actualRank)))
  return (
    <div className="mb-6 rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
      <h2 className="mb-1 text-xs font-semibold uppercase tracking-wider text-gray-500">
        Our rank vs. how the season actually finished
      </h2>
      <p className="mb-3 text-[11px] leading-relaxed text-gray-600">
        Every dot is a player; closer to the diagonal is a better call. Highlighted dots are our
        highest-conviction disagreements with ADP that season (the &ldquo;fades&rdquo;) — where the
        airtight independent claim lives:{" "}
        <span className="text-[#10b981]">green = hit</span>,{" "}
        <span className="text-rose-400">red = miss</span>,{" "}
        <span className="text-amber-500">amber = push</span>.
      </p>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="#1a1a1a" />
            <XAxis
              type="number"
              dataKey="ourRank"
              name="Our rank"
              domain={[1, maxRank]}
              stroke="#6b7280"
              fontSize={11}
              label={{ value: "Our rank (within position)", position: "insideBottom", offset: -4, fill: "#6b7280", fontSize: 11 }}
            />
            <YAxis
              type="number"
              dataKey="actualRank"
              name="Actual finish"
              domain={[1, maxRank]}
              stroke="#6b7280"
              fontSize={11}
              label={{ value: "Actual finish", angle: -90, position: "insideLeft", fill: "#6b7280", fontSize: 11 }}
            />
            <ReferenceLine
              segment={[{ x: 1, y: 1 }, { x: maxRank, y: maxRank }]}
              stroke="#374151"
              strokeDasharray="4 4"
            />
            <Tooltip
              cursor={{ strokeDasharray: "3 3" }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const row = payload[0].payload as TrackRecordRow
                return (
                  <div className="rounded border border-[#262626] bg-[#0f0f0f] px-2.5 py-1.5 text-xs text-gray-300">
                    <div className="font-medium text-gray-100">
                      {row.playerName} · {row.position}
                    </div>
                    <div>
                      Our rank {posRank(row.position, row.ourRank)} · ADP rank{" "}
                      {posRank(row.position, row.adpRank)} · actual {posRank(row.position, row.actualRank)}
                    </div>
                    {row.isFade && (
                      <div
                        className={
                          row.fadeResult === "hit"
                            ? "text-[#10b981]"
                            : row.fadeResult === "miss"
                              ? "text-rose-400"
                              : "text-amber-500"
                        }
                      >
                        high-conviction fade · {row.fadeResult ?? "—"}
                      </div>
                    )}
                  </div>
                )
              }}
            />
            <Scatter data={rows} shape={<FadeDot />} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

/** All three ranks in this table are WITHIN-POSITION (the scatter chart's axis already says so —
 *  "Our rank (within position)" — but the table's bare "1"/"2"/"3" reads as an overall rank,
 *  especially on the "All" position tab where several different positions' #1s all show "1"). Prefix
 *  with the position so it reads unambiguously regardless of which tab is active, e.g. "QB1"/"RB12". */
function posRank(pos: string, rank: number | null): string {
  return rank == null ? "—" : `${pos}${rank}`
}

function TrackRecordTable({ rows }: { rows: TrackRecordRow[] }) {
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZES[0])
  const sorted = useMemo(() => rows.slice().sort((a, b) => a.ourRank - b.ourRank), [rows])
  const paged =
    pageSize === ALL_ROWS ? sorted : sorted.slice(page * pageSize, (page + 1) * pageSize)

  if (rows.length === 0) {
    return (
      <EmptyBlock
        title="No scored players for this position"
        detail="Try a different position tab or season."
      />
    )
  }
  return (
    <div className="rounded-lg border border-[#262626] bg-[#0f0f0f]">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-[#262626] text-[10px] uppercase tracking-wider text-gray-500">
              {/* Sticky so a player's identity stays visible while scrolling right on mobile, where
                  this table is wider than the screen — otherwise a scrolled-right row is anonymous
                  numbers with no name attached. */}
              <th className="sticky left-0 z-10 bg-[#0f0f0f] px-3 py-2">Player</th>
              <th className="px-3 py-2">Pos</th>
              <th className="px-3 py-2 text-right">Our rank (pos)</th>
              <th className="px-3 py-2 text-right">Our pts</th>
              <th className="px-3 py-2 text-right">ADP rank (pos)</th>
              <th className="px-3 py-2 text-right">ADP</th>
              <th className="px-3 py-2 text-right">Actual rank (pos)</th>
              <th className="px-3 py-2 text-right">Actual pts</th>
              <th className="px-3 py-2">
                <InfoTip label="Fade">{GLOSSARY.fade}</InfoTip>
              </th>
            </tr>
          </thead>
          <tbody>
            {paged.map((r) => (
              <tr key={r.playerId} className="border-b border-[#1a1a1a] last:border-0">
                <td className="sticky left-0 bg-[#0f0f0f] px-3 py-2">
                  <Link
                    href={`/fantasy/player/${r.playerId}`}
                    className="text-gray-200 hover:text-[#10b981] transition-colors"
                  >
                    {r.playerName}
                  </Link>
                </td>
                <td className="px-3 py-2">
                  <PosBadge pos={r.position} />
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-300">{posRank(r.position, r.ourRank)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-400">{num(r.ourPoints)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-300">{posRank(r.position, r.adpRank)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-400">{num(r.adp)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-300">{posRank(r.position, r.actualRank)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-400">{num(r.actualPoints)}</td>
                <td className="px-3 py-2">
                  <FadeBadge isFade={r.isFade} fadeResult={r.fadeResult} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="border-t border-[#262626] p-3">
        <Pagination
          page={page}
          pageSize={pageSize}
          total={sorted.length}
          onPage={setPage}
          onPageSize={setPageSize}
        />
      </div>
    </div>
  )
}

export function FantasyTrackRecordPage() {
  const { data: manifest, isLoading: manifestLoading, error: manifestError } = useTrackRecordManifest()
  const seasons = manifest?.seasons ?? []
  const [season, setSeason] = useState<number | null>(null)
  const activeSeason = season ?? seasons[seasons.length - 1] ?? null
  const { data: seasonRows, isLoading: seasonLoading } = useTrackRecordSeason(activeSeason)
  const [position, setPosition] = useState("All")

  const filteredRows = useMemo(() => {
    const rows = seasonRows ?? []
    return position === "All" ? rows : rows.filter((r) => r.position === position)
  }, [seasonRows, position])

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <SurfaceHeader
        title="Track Record"
        blurb="Our past-season fantasy projections, graded against what actually happened — model rank vs. that season's ADP vs. the realized finish. The full picture, wins and losses both."
      />

      {manifestLoading && <LoadingBlock label="Loading the track record…" />}
      {!manifestLoading && (manifestError || !manifest || seasons.length === 0) && (
        <EmptyBlock
          title="Track record not published yet"
          detail="The receipts export hasn't landed yet — check back soon."
        />
      )}

      {manifest && seasons.length > 0 && (
        <>
          <HeadlineBanner headline={manifest.headline} />
          <LockedCurrentSeasonCard lockedSeason={manifest.lockedSeason} />

          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-1.5">
              {seasons.map((s) => (
                <button
                  key={s}
                  onClick={() => setSeason(s)}
                  className={`rounded border px-2.5 py-1 text-xs font-medium transition-colors ${
                    s === activeSeason
                      ? "border-[#10b981]/50 bg-[#10b981]/10 text-[#10b981]"
                      : "border-[#262626] bg-[#0f0f0f] text-gray-400 hover:text-gray-200"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
            <PositionTabs value={position} onChange={setPosition} positions={[...SKILL_POSITIONS]} />
          </div>

          {seasonLoading && <LoadingBlock label="Loading the season…" />}
          {!seasonLoading && seasonRows && (
            <>
              {activeSeason != null && manifest.adpSourceBySeason[String(activeSeason)] === "mfl" && (
                <p className="mb-4 rounded border border-[#262626] bg-[#0f0f0f] px-3 py-2 text-[11px] leading-relaxed text-gray-500">
                  Fantasy Football Calculator has no ADP archive for {activeSeason} — the ADP column
                  below is sourced from MyFantasyLeague instead, a second independent real-draft
                  consensus.
                </p>
              )}
              {activeSeason != null && manifest.adpSourceBySeason[String(activeSeason)] === undefined && (
                <p className="mb-4 rounded border border-[#262626] bg-[#0f0f0f] px-3 py-2 text-[11px] leading-relaxed text-gray-500">
                  No ADP archive is available for {activeSeason} from either source — this season shows
                  our projection vs. the realized outcome only, no ADP column or fade highlighting.
                </p>
              )}
              <RankScatter rows={filteredRows} />
              <TrackRecordTable rows={filteredRows} />
            </>
          )}
        </>
      )}
    </div>
  )
}
