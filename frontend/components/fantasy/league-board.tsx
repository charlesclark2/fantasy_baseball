"use client"

// NF3 — League Board (value over replacement). The draft-relevant cross-position view: what a
// player is worth ABOVE the freely-available player at his position in YOUR league, which is the
// only honest way to compare a quarterback to a running back.
//
// It leads with the replacement-level table on purpose — VOR is only as trustworthy as its
// baseline, so the baseline is shown rather than assumed. "Startable" is derived from the board
// itself (players scoring above their position's replacement level), which is exactly the
// definition the scoring engine uses.

import { useMemo, useState } from "react"
import { useFantasyBoard, useFantasyManifest, useFormatSelection } from "@/lib/fantasy-queries"
import type { Player } from "@/lib/draft-optimizer"
import {
  ADP_DELTA_LABEL,
  AdpDelta,
  adpPositionRanks,
  EmptyBlock,
  FormatSelector,
  GLOSSARY,
  InfoTip,
  LoadingBlock,
  PosBadge,
  PositionTabs,
  ProvenanceLine,
  RookieBadge,
  ALL_POSITIONS,
  SKILL_POSITIONS,
  SurfaceHeader,
  UncertaintyNote,
  num,
  int,
  teamLabel,
} from "@/components/fantasy/shared"

interface PosSummary {
  pos: string
  replacement: number
  startable: number
  pool: number
  /** The player actually sitting at replacement level — the yardstick made concrete. */
  replacementPlayer: Player | null
}

export function LeagueBoard() {
  const { data: manifest, isLoading: manifestLoading, error: manifestError } = useFantasyManifest()
  const { configName, size, setConfigName, setSize } = useFormatSelection(manifest)
  const { data: board, isLoading: boardLoading } = useFantasyBoard(configName, size)
  const [pos, setPos] = useState("All")

  const config = manifest?.configs.find((c) => c.name === configName)

  // ⭐ NF1.6: K/DST now carry a real (BASE) projection with points and VOR, so they belong on the
  // value board. The `pts`/`vor != null` tests still exclude a genuinely unprojected gap-fill row.
  const ranked = useMemo(
    () =>
      (board ?? []).filter(
        (p) => p.pts != null && p.vor != null && (ALL_POSITIONS as readonly string[]).includes(p.pos),
      ),
    [board],
  )

  // Per-position replacement level + how many players clear it league-wide (= startable at that
  // position once flex/superflex demand is allocated).
  //
  // ⚠️ SKILL positions only, deliberately — this panel is NOT merely a summary of the rows below.
  // Replacement level is the yardstick a drafter reasons with ("is this worth a pick here?"), and
  // that reasoning only applies where the position is genuinely contested. Every league starts
  // exactly one K and one DST off a pool that is near-flat and near-unpredictable, so their
  // replacement level is a real number that supports no decision — showing it invites the reader to
  // treat a ~1-point gap between DST3 and DST7 as a draft-day edge. K/DST still rank in the table
  // below (and still carry VOR, which is what correctly sorts them LAST).
  const summary = useMemo<PosSummary[]>(() => {
    const out: PosSummary[] = []
    for (const p of SKILL_POSITIONS) {
      const atPos = ranked.filter((r) => r.pos === p)
      if (atPos.length === 0) continue
      const replacement = atPos[0].repl ?? 0
      const startable = atPos.filter((r) => (r.pts ?? 0) > replacement).length
      // The replacement level IS the points of the first non-starter, so that player is the one
      // immediately after the startable block in points order. Naming him turns an abstract
      // baseline into something a drafter can picture ("better than THAT guy").
      const byPoints = atPos.slice().sort((a, b) => (b.pts ?? 0) - (a.pts ?? 0))
      out.push({
        pos: p,
        replacement,
        startable,
        pool: atPos.length,
        replacementPlayer: byPoints[startable] ?? null,
      })
    }
    return out
  }, [ranked])

  const rows = useMemo(() => {
    const filtered = pos === "All" ? ranked : ranked.filter((r) => r.pos === pos)
    return filtered.slice().sort((a, b) => (b.vor ?? 0) - (a.vor ?? 0))
  }, [ranked, pos])

  const maxVor = useMemo(() => Math.max(1, ...rows.map((r) => r.vor ?? 0)), [rows])
  const hasAdp = useMemo(() => rows.some((r) => r.adp != null), [rows])

  // Filtered to one position, the row index is a rank WITHIN that position, so it must be compared
  // against the room's rank within the position rather than against ADP's overall pick number.
  // Null on "All", where the row index and ADP are already the same scale. See `adpPositionRanks`.
  const adpPosRank = useMemo(
    () => (pos === "All" ? null : adpPositionRanks(rows)),
    [rows, pos],
  )

  // Drop-off to the next player at the same position — the "if I wait, this is what I lose" number
  // the draft optimizer prices as VONA. Computed over the FULL board, not the filtered view.
  const dropoff = useMemo(() => {
    const byPos = new Map<string, Player[]>()
    for (const p of ranked) {
      const arr = byPos.get(p.pos) ?? []
      arr.push(p)
      byPos.set(p.pos, arr)
    }
    const out = new Map<string, number>()
    for (const arr of byPos.values()) {
      arr.sort((a, b) => (b.vor ?? 0) - (a.vor ?? 0))
      arr.forEach((p, i) => {
        const next = arr[i + 1]
        if (next) out.set(p.id, (p.vor ?? 0) - (next.vor ?? 0))
      })
    }
    return out
  }, [ranked])

  // The first row at or below replacement — everything under it is free-agent-equivalent value.
  const firstBelowReplacement = rows.findIndex((r) => (r.vor ?? 0) <= 0)

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <SurfaceHeader
        title="League Board"
        blurb="Value over replacement for your league: what each player is worth above the best freely-available player at his position, once your roster shape and league size decide how many of each position actually start."
      >
        <div className="mt-2">
          <ProvenanceLine
            season={manifest?.season ?? 2026}
            generatedAt={manifest?.generated_at}
            extra={config ? `${config.label} · ${size ?? "—"} teams` : null}
          />
        </div>
      </SurfaceHeader>

      {manifestLoading && <LoadingBlock label="Loading league formats…" />}

      {!manifestLoading && (manifestError || !manifest) && (
        <EmptyBlock
          title="The league board isn't available yet"
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

          {boardLoading && <LoadingBlock label="Building the value board…" />}

          {!boardLoading && ranked.length > 0 && (
            <>
              {/* replacement-level transparency */}
              <div className="mb-6 rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
                <h2 className="text-sm font-semibold text-gray-200">Replacement level</h2>
                <p className="mt-1 max-w-3xl text-xs leading-relaxed text-gray-500">
                  A player&apos;s value is his projected points minus the points of the first player at
                  his position who does <em>not</em>{" "}
                  start anywhere in the league. That baseline moves with your format: more teams, or a
                  superflex spot, pushes it deeper and raises the position&apos;s value.
                </p>
                <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {summary.map((s) => (
                    <div key={s.pos} className="rounded border border-[#1f1f1f] bg-[#0a0a0a] p-3">
                      <div className="flex items-center justify-between">
                        <PosBadge pos={s.pos} />
                        <span className="text-[10px] text-gray-600">{s.pool} projected</span>
                      </div>
                      <div className="mt-2 text-lg font-semibold text-gray-100">
                        {num(s.replacement)}
                      </div>
                      <div className="text-[11px] text-gray-500">
                        replacement pts · {s.startable} startable
                      </div>
                      {s.replacementPlayer && (
                        <div className="mt-2 border-t border-[#1f1f1f] pt-2 text-[11px] leading-tight">
                          <InfoTip label={<span className="text-gray-600">at that level</span>}>
                            {GLOSSARY.replacementPlayer}
                          </InfoTip>
                          <div className="mt-0.5 truncate text-gray-300" title={s.replacementPlayer.name}>
                            {s.replacementPlayer.name}
                          </div>
                          <div className="text-gray-600">
                            {teamLabel(s.replacementPlayer)} · {s.pos}
                            {s.replacementPlayer.posRank}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div className="mb-4">
                <PositionTabs value={pos} onChange={setPos} />
              </div>

              <div className="overflow-x-auto rounded-lg border border-[#262626]">
                <table className="w-full min-w-[760px] text-left text-xs">
                  <thead className="bg-[#0f0f0f] text-gray-500">
                    <tr>
                      <th className="px-3 py-2 font-medium">#</th>
                      <th className="px-3 py-2 font-medium">Player</th>
                      <th className="px-3 py-2 font-medium">Pos</th>
                      <th className="px-3 py-2 font-medium">Team</th>
                      <th className="px-3 py-2 text-right font-medium">Bye</th>
                      <th className="px-3 py-2 text-right font-medium">Proj pts</th>
                      <th className="px-3 py-2 text-right font-medium">
                        <InfoTip label="Replacement">{GLOSSARY.replacement}</InfoTip>
                      </th>
                      <th className="px-3 py-2 text-right font-medium">
                        <InfoTip label="VOR">{GLOSSARY.vor}</InfoTip>
                      </th>
                      <th className="px-3 py-2 font-medium">Value above replacement</th>
                      <th className="px-3 py-2 text-right font-medium">
                        <InfoTip label="Next at pos">{GLOSSARY.nextAtPos}</InfoTip>
                      </th>
                      {hasAdp && (
                        <>
                          <th className="px-3 py-2 text-right font-medium">
                            <InfoTip label="ADP">
                              {GLOSSARY.adp}
                              {config?.adpFormat ? ` Sample: ${config.adpFormat}, ${size}-team.` : ""}
                            </InfoTip>
                          </th>
                          <th className="px-3 py-2 text-right font-medium">
                            <InfoTip label={ADP_DELTA_LABEL}>{GLOSSARY.adpDelta}</InfoTip>
                          </th>
                        </>
                      )}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1a1a1a]">
                    {rows.map((p, i) => (
                      <tr
                        key={p.id}
                        className={`hover:bg-[#0f0f0f] ${
                          i === firstBelowReplacement ? "border-t-2 border-t-[#10b981]/40" : ""
                        }`}
                      >
                        <td className="px-3 py-2 text-gray-600">{i + 1}</td>
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
                        <td className="px-3 py-2 text-right text-gray-300">{num(p.pts)}</td>
                        <td className="px-3 py-2 text-right text-gray-500">{num(p.repl)}</td>
                        <td className="px-3 py-2 text-right font-semibold text-gray-100">
                          {num(p.vor)}
                        </td>
                        <td className="w-44 px-3 py-2">
                          <div className="h-1.5 w-full rounded-full bg-[#1a1a1a]">
                            <div
                              className="h-1.5 rounded-full bg-emerald-500/50"
                              style={{
                                width: `${Math.max(0, Math.min(100, ((p.vor ?? 0) / maxVor) * 100))}%`,
                              }}
                            />
                          </div>
                          {p.vorP10 != null && p.vorP90 != null && (
                            <div className="mt-1 text-[10px] text-gray-600">
                              80%: {int(p.vorP10)} to {int(p.vorP90)}
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right text-gray-500">
                          {dropoff.has(p.id) ? num(dropoff.get(p.id)) : "—"}
                        </td>
                        {hasAdp && (
                          <>
                            <td className="px-3 py-2 text-right text-gray-400">
                              {p.adp != null ? num(p.adp) : "—"}
                            </td>
                            <td className="px-3 py-2 text-right">
                              {/* the value board's own order is the rank we compare ADP against */}
                              <AdpDelta
                                delta={(() => {
                                  const ref = adpPosRank ? (adpPosRank.get(p.id) ?? null) : p.adp ?? null
                                  return ref != null ? ref - (i + 1) : null
                                })()}
                              />
                            </td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <p className="mt-3 text-[11px] text-gray-600">
                The green line marks where value crosses replacement — players below it project no
                better than what should be available for free in your league.{" "}
                <span className="text-gray-500">Next at pos</span> is how much value you give up by
                passing on this player and taking the next one at his position instead.
              </p>

              <div className="mt-6">
                <UncertaintyNote>
                  <p className="mt-2">
                    <span className="font-semibold text-gray-300">Read the value gaps, not the
                    decimals.</span>{" "}
                    A two-point difference in VOR is noise inside these ranges; a thirty-point gap, or a
                    steep drop to the next player at a position, is the signal worth drafting on. The
                    80% band under each bar is carried straight through from the projection, shifted by
                    the replacement level.
                  </p>
                  <p className="mt-2">
                    <span className="font-semibold text-gray-300">Kickers and defences.</span> They
                    rank in the table but are left out of the replacement-level panel above. Every
                    league starts one of each off a pool that is nearly flat and nearly
                    unpredictable, so their baseline is a real number that supports no decision. Their
                    small value over replacement is the honest answer, and it is what correctly sorts
                    them to the end of the board.
                  </p>
                  {hasAdp && (
                    <p className="mt-2">
                      <span className="font-semibold text-gray-300">About the ADP column.</span> ADP
                      is where the public is drafting these players, matched to this format and league
                      size, shown so you can see where this value board and the room disagree. It is a
                      reference point, not a scoreboard — we make no claim to beat it.
                    </p>
                  )}
                </UncertaintyNote>
              </div>
            </>
          )}

          {!boardLoading && ranked.length === 0 && (
            <EmptyBlock
              title="No board for this format yet"
              detail="This scoring format and league size combination hasn't been published. Try another format or size."
            />
          )}
        </>
      )}
    </div>
  )
}
