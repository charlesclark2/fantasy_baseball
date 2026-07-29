"use client"

// NF3 — Rankings (browse). The same season projection, RE-SCORED for a chosen league format and
// size, then ranked. Overall order is by value over replacement (a cross-position ranking is only
// meaningful once positional scarcity is accounted for); a position tab ranks within that position
// by projected league points.
//
// The format matters: switching to superflex or full-PPR genuinely reorders the board because the
// underlying raw stat line is re-scored, not re-weighted cosmetically.

import { useMemo, useState } from "react"
import { Search } from "lucide-react"
import { useFantasyBoard, useFantasyManifest, useFormatSelection } from "@/lib/fantasy-queries"
import type { Player } from "@/lib/draft-optimizer"
import {
  EmptyBlock,
  FormatSelector,
  IntervalBar,
  LoadingBlock,
  PosBadge,
  PositionTabs,
  ProvenanceLine,
  RookieBadge,
  SKILL_POSITIONS,
  SurfaceHeader,
  UncertaintyNote,
  num,
  int,
  teamLabel,
} from "@/components/fantasy/shared"

export function RankingsBoard() {
  const { data: manifest, isLoading: manifestLoading, error: manifestError } = useFantasyManifest()
  const { configName, size, setConfigName, setSize } = useFormatSelection(manifest)
  const { data: board, isLoading: boardLoading } = useFantasyBoard(configName, size)
  const [pos, setPos] = useState("Overall")
  const [q, setQ] = useState("")

  const config = manifest?.configs.find((c) => c.name === configName)

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase()
    // K/DST carry no projection (offensive skill only) — they exist on the board purely so the
    // draft tracker can record those picks, and must never appear in a ranked list.
    const ranked = (board ?? []).filter((p) => p.pts != null && (SKILL_POSITIONS as readonly string[]).includes(p.pos))
    const filtered = ranked
      .filter((p) => (pos === "Overall" ? true : p.pos === pos))
      .filter((p) => (needle ? p.name.toLowerCase().includes(needle) : true))
    return pos === "Overall"
      ? filtered.slice().sort((a, b) => a.ovrRank - b.ovrRank)
      : filtered.slice().sort((a, b) => a.posRank - b.posRank)
  }, [board, pos, q])

  // Shared interval domain over the visible rows, so the bars are comparable down the column.
  const domain = useMemo(() => {
    let min = Infinity
    let max = -Infinity
    for (const p of rows) {
      if (p.ptsP10 != null) min = Math.min(min, p.ptsP10)
      if (p.ptsP90 != null) max = Math.max(max, p.ptsP90)
    }
    return Number.isFinite(min) && Number.isFinite(max) ? { min, max } : null
  }, [rows])

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <SurfaceHeader
        title="Rankings"
        blurb="The season projection scored for your league's format and size, then ranked. Overall order is by value over replacement, so a quarterback and a receiver are comparable on one board."
      >
        <div className="mt-2">
          <ProvenanceLine
            season={manifest?.season ?? 2026}
            generatedAt={manifest?.generated_at}
            extra={config?.label}
          />
        </div>
      </SurfaceHeader>

      {manifestLoading && <LoadingBlock label="Loading league formats…" />}

      {!manifestLoading && (manifestError || !manifest) && (
        <EmptyBlock
          title="Rankings aren't available yet"
          detail="The league boards haven't been published to this surface yet. Please check back shortly."
        />
      )}

      {manifest && (
        <>
          <div className="mb-5 rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
            <FormatSelector
              manifest={manifest}
              configName={configName}
              size={size}
              onConfig={setConfigName}
              onSize={setSize}
            />
          </div>

          <div className="mb-4 flex flex-wrap items-center gap-3">
            <PositionTabs value={pos} onChange={setPos} allLabel="Overall" />
            <div className="relative">
              <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-600" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search player"
                className="w-48 rounded border border-[#262626] bg-[#0f0f0f] py-1.5 pl-7 pr-2 text-xs text-gray-200 placeholder:text-gray-600 focus:border-[#10b981] focus:outline-none"
              />
            </div>
          </div>

          {boardLoading && <LoadingBlock label="Scoring the board…" />}

          {!boardLoading && rows.length === 0 && (
            <EmptyBlock
              title="No players match"
              detail="Try clearing the search box or switching position."
            />
          )}

          {!boardLoading && rows.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-[#262626]">
              <table className="w-full min-w-[720px] text-left text-xs">
                <thead className="bg-[#0f0f0f] text-gray-500">
                  <tr>
                    <th className="px-3 py-2 font-medium">{pos === "Overall" ? "Rank" : `${pos} #`}</th>
                    <th className="px-3 py-2 font-medium">Player</th>
                    <th className="px-3 py-2 font-medium">Pos</th>
                    <th className="px-3 py-2 font-medium">Team</th>
                    <th className="px-3 py-2 text-right font-medium">Bye</th>
                    <th className="px-3 py-2 text-right font-medium">G</th>
                    <th className="px-3 py-2 text-right font-medium">Proj pts</th>
                    <th className="px-3 py-2 font-medium">80% range</th>
                    <th className="px-3 py-2 text-right font-medium">VOR</th>
                    {pos === "Overall" && <th className="px-3 py-2 text-right font-medium">Pos rank</th>}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1a1a1a]">
                  {rows.map((p: Player) => (
                    <tr key={p.id} className="hover:bg-[#0f0f0f]">
                      <td className="px-3 py-2 font-medium text-gray-500">
                        {pos === "Overall" ? p.ovrRank : p.posRank}
                      </td>
                      <td className="px-3 py-2">
                        <span className="flex items-center gap-1.5">
                          <span className="font-medium text-gray-200">{p.name}</span>
                          {p.rookie && <RookieBadge />}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <PosBadge pos={p.pos} />
                      </td>
                      <td className="px-3 py-2 text-gray-400">{teamLabel(p)}</td>
                      <td className="px-3 py-2 text-right text-gray-500">{p.bye ?? "—"}</td>
                      <td className="px-3 py-2 text-right text-gray-400">{num(p.g)}</td>
                      <td className="px-3 py-2 text-right font-semibold text-gray-100">{num(p.pts)}</td>
                      <td className="w-40 px-3 py-2">
                        {p.ptsP10 != null && p.ptsP90 != null && domain ? (
                          <>
                            <div className="text-[11px] text-gray-400">
                              {int(p.ptsP10)}–{int(p.ptsP90)}
                            </div>
                            <IntervalBar
                              p10={p.ptsP10}
                              point={p.pts}
                              p90={p.ptsP90}
                              min={domain.min}
                              max={domain.max}
                            />
                          </>
                        ) : (
                          <span className="text-[11px] text-gray-600">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right text-gray-300">{num(p.vor)}</td>
                      {pos === "Overall" && (
                        <td className="px-3 py-2 text-right text-gray-500">
                          {p.pos}
                          {p.posRank}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="mt-6">
            <UncertaintyNote>
              <p className="mt-2">
                <span className="font-semibold text-gray-300">Why the order changes with format.</span>{" "}
                Each board re-scores the same projected stat line under your league&apos;s rules, then
                re-derives replacement level for that roster shape and league size — so superflex lifts
                quarterbacks and full-PPR lifts pass-catchers for a real reason, not a cosmetic tweak.
              </p>
            </UncertaintyNote>
          </div>
        </>
      )}
    </div>
  )
}
