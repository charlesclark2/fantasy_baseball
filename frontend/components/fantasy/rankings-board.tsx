"use client"

// NF3 — Rankings (browse). The same season projection, RE-SCORED for a chosen league format and
// size, then ranked. Overall order is by value over replacement (a cross-position ranking is only
// meaningful once positional scarcity is accounted for); a position tab ranks within that position
// by projected league points.
//
// The format matters: switching to superflex or full-PPR genuinely reorders the board because the
// underlying raw stat line is re-scored, not re-weighted cosmetically.
//
// ADP is shown as a REFERENCE — what the room is doing — with a delta so the disagreements are
// findable. It is deliberately not framed as an edge: we do not claim to beat it (see NF-D3), and
// the honest read is "here is where we differ, and here is how sure we are", not "here is value".

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { Download, Search } from "lucide-react"
import {
  useFantasyManifest,
  useFormatSelection,
  useResolvedBoard,
  useSavedLeagues,
} from "@/lib/fantasy-queries"
import { assignTiers, type Player } from "@/lib/draft-optimizer"
import {
  ADP_DELTA_LABEL,
  ALL_ROWS,
  AdpDelta,
  adpPositionRanks,
  EmptyBlock,
  FormatSelector,
  GLOSSARY,
  InfoTip,
  IntervalBar,
  LockChip,
  LoadingBlock,
  Pagination,
  PosBadge,
  PositionTabs,
  RangeCell,
  ProvenanceLine,
  RookieBadge,
  ALL_POSITIONS,
  LOW_PREDICTABILITY_POSITIONS,
  SurfaceHeader,
  MarketLeanNote,
  UncertaintyNote,
  UpgradeBanner,
  downloadCsv,
  num,
  numOrLock,
  int,
  teamLabel,
} from "@/components/fantasy/shared"

/** Our rank for a row, given which tab is active. */
const rankOf = (p: Player, pos: string) => (pos === "Overall" ? p.ovrRank : p.posRank)

export function RankingsBoard() {
  const { data: manifest, isLoading: manifestLoading, error: manifestError } = useFantasyManifest()
  // NF-C0b: a saved hand-entered league ranks through the identical Player[] interface.
  const { data: savedLeagues } = useSavedLeagues()
  const { configName, size, setConfigName, setSize } = useFormatSelection(manifest, savedLeagues)
  const { board, isLoading: boardLoading } = useResolvedBoard(configName, size)
  const [pos, setPos] = useState("Overall")
  const [q, setQ] = useState("")
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState<number>(50)

  const config = manifest?.configs.find((c) => c.name === configName)

  // The board in its ranked order, BEFORE any search. Tiers and ranks are properties of the board,
  // so they are derived here and merely filtered below — searching never renumbers or re-tiers.
  // ⭐ NF1.6: K/DST now carry a real (BASE) projection, so they rank here like every other position.
  // The `pts != null` test is what still excludes a genuinely unprojected row — a gap-fill K/DST
  // placeholder for a team the projection missed — so an absent projection is shown as absent
  // rather than as a zero.
  const ranked = useMemo(() => {
    const projected = (board ?? []).filter(
      (p) => p.pts != null && (ALL_POSITIONS as readonly string[]).includes(p.pos),
    )
    const scoped = projected.filter((p) => (pos === "Overall" ? true : p.pos === pos))
    return pos === "Overall"
      ? scoped.slice().sort((a, b) => a.ovrRank - b.ovrRank)
      : scoped.slice().sort((a, b) => a.posRank - b.posRank)
  }, [board, pos])

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return needle ? ranked.filter((p) => p.name.toLowerCase().includes(needle)) : ranked
  }, [ranked, q])

  // Tiers: grouped by an unusually large drop to the next player, using the SAME gap-based helper
  // the draft optimizer scores with (lib/draft-optimizer.assignTiers) so a tier means one thing
  // across the product. Computed on the full ranked set BEFORE search/paging — a tier is a property
  // of the board, so it must not shift when you search or turn a page.
  //
  // ⚠️ ONLY above-replacement players are tiered, and that is load-bearing rather than tidy-minded.
  // `assignTiers` splits on a gap wider than mean + k·std of consecutive gaps; run over all ~716
  // players the long flat tail collapses that threshold, and the top of the board fragments into
  // one tier per player (36 tiers, ranks 1-7 each alone = useless). Restricted to the startable
  // pool (~84 here) the same k=1.0 yields ~10 genuine tiers. It is also the right definition:
  // below replacement there is no value to group. Sub-replacement players get no tier.
  //
  // ⭐ NF-D19: `assignTiers` also enforces MIN/MAX TIER SIZE bounds, scaled to the pool size rather
  // than a fixed count — a lone player at the top (T1=Bijan alone) merges into its neighbor, and a
  // long flat stretch that never clears the gap threshold (which, at a flat min-size-only floor, was
  // swallowing nearly a whole full-PPR WR pool into one or two tiers) gets split at its own largest
  // internal gaps instead of staying one giant undifferentiated tier. See the bounds note on
  // `assignTiers` itself.
  //
  // Overall tiers on VOR (the cross-position value axis the tab is ordered by); a position tab
  // tiers on league points, which is that tab's own ordering.
  //
  // ⚠️ K and D/ST are NOT tiered, and that is a statement about the model rather than a UI choice.
  // A tier break means "an unusually large drop" — it is only meaningful when the gaps carry signal.
  // Kickers and defences project onto a near-flat board (the whole DST field spans ~10 points, and
  // held-out rank correlation is ~0.32 for DST and ~0.23 among startable kickers), so `assignTiers`
  // is reading NOISE and splitting on it: it will happily crown a "T1" kicker whose separation from
  // T2 is well inside the interval either of them carries. That badge then reads as a confident
  // rating on the one part of the board that has earned the least confidence. No tier is the honest
  // rendering — these rows still rank, and the prose below says how to read that ranking.
  const tierOf = useMemo(() => {
    const m = new Map<string, number>()
    const draftable = ranked.filter(
      (p) => (p.vor ?? 0) > 0 && !LOW_PREDICTABILITY_POSITIONS.includes(p.pos),
    )
    if (draftable.length === 0) return m
    const vals = draftable.map((p) => (pos === "Overall" ? (p.vor ?? 0) : (p.pts ?? 0)))
    const tiers = assignTiers(vals)
    draftable.forEach((p, i) => m.set(p.id, tiers[i] ?? 1))
    return m
  }, [ranked, pos])

  // Any filter/format change invalidates the current page offset.
  useEffect(() => setPage(0), [pos, q, configName, size])

  const paged = useMemo(
    () => (pageSize === ALL_ROWS ? rows : rows.slice(page * pageSize, page * pageSize + pageSize)),
    [rows, page, pageSize],
  )

  // Which rows start a NEW tier badge. DST/K rows carry no tier ("—"), so the boundary must compare
  // against the last TIERED row seen, not the immediately-preceding row — otherwise every DST/K
  // interruption makes the next skill player re-show the badge, and one tier reads as several
  // same-numbered tiers (NF-D19). A tier is one contiguous badge regardless of what untiered rows
  // are interleaved.
  const startsTierAt = useMemo(() => {
    let lastTier: number | null = null
    return paged.map((p) => {
      const t = tierOf.get(p.id) ?? null
      if (t == null) return false
      const starts = lastTier !== t
      lastTier = t
      return starts
    })
  }, [paged, tierOf])

  // Shared interval domain over the PAGED rows, so the bars are comparable down the visible column.
  const domain = useMemo(() => {
    let min = Infinity
    let max = -Infinity
    for (const p of paged) {
      if (p.ptsP10 != null) min = Math.min(min, p.ptsP10)
      if (p.ptsP90 != null) max = Math.max(max, p.ptsP90)
    }
    return Number.isFinite(min) && Number.isFinite(max) ? { min, max } : null
  }, [paged])

  const hasAdp = useMemo(() => rows.some((p) => p.adp != null), [rows])

  // On a position tab, our rank is 1..n WITHIN the position, so it must be compared against the
  // room's rank within the position — not against ADP, which is an overall pick number. Null on the
  // Overall tab, where our rank and ADP are already the same scale. See `adpPositionRanks`.
  const adpPosRank = useMemo(
    () => (pos === "Overall" ? null : adpPositionRanks(ranked)),
    [ranked, pos],
  )
  /** The room's position for this row, on whichever scale the active tab ranks in. */
  const adpRefOf = (p: Player) => (adpPosRank ? (adpPosRank.get(p.id) ?? null) : p.adp ?? null)

  const exportCsv = () => {
    downloadCsv(
      `credence-rankings-${configName}-${size}team-${pos.toLowerCase()}.csv`,
      ["rank", "tier", "player", "pos", "team", "bye", "games", "proj_pts", "pts_p10", "pts_p90",
       "vor", "pos_rank", "adp", "vs_adp", "rookie", "range_basis"],
      rows.map((p) => {
        const rank = rankOf(p, pos)
        return [
          rank, tierOf.get(p.id) ?? "", p.name, p.pos, teamLabel(p), p.bye ?? null, p.g, p.pts,
          p.ptsP10 ?? null, p.ptsP90 ?? null, p.vor, p.posRank, p.adp ?? null,
          // same scale as the rendered column — see adpRefOf
          adpRefOf(p) != null ? Math.round((adpRefOf(p) as number) - rank) : null,
          p.rookie ? "yes" : "no",
          // carried so a downloaded board still says which ranges are class-level, not per-player
          p.rookie ? "class-level" : "player",
        ]
      }),
    )
  }

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

      {/* E9.56 — page-level lock state rides on the MANIFEST: the board endpoint returns a bare
          array, and wrapping it would be the NF-C0 response-shape break. Per-cell chips come from
          each row's own `locked` marker. */}
      {manifest?.locked && (
        <UpgradeBanner season={manifest.season} upgrade={manifest.upgrade} />
      )}

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
              savedLeagues={savedLeagues}
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
                className="w-48 rounded border border-[#262626] bg-[#0f0f0f] py-1.5 pl-7 pr-2 text-base sm:text-xs text-gray-200 placeholder:text-gray-600 focus:border-[#10b981] focus:outline-none"
              />
            </div>
            <button
              onClick={exportCsv}
              disabled={rows.length === 0}
              className="ml-auto flex items-center gap-1.5 rounded border border-[#262626] bg-[#0f0f0f] px-2.5 py-1.5 text-xs text-gray-400 transition-colors hover:text-gray-200 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Download className="h-3.5 w-3.5" />
              Export CSV
            </button>
          </div>

          {boardLoading && <LoadingBlock label="Scoring the board…" />}

          {!boardLoading && rows.length === 0 && (
            <EmptyBlock
              title="No players match"
              detail="Try clearing the search box or switching position."
            />
          )}

          {!boardLoading && rows.length > 0 && (
            <>
              <div className="mb-3">
                <Pagination
                  page={page}
                  pageSize={pageSize}
                  total={rows.length}
                  onPage={setPage}
                  onPageSize={setPageSize}
                />
              </div>

              <div className="overflow-x-auto rounded-lg border border-[#262626]">
                <table className="w-full min-w-[860px] text-left text-xs">
                  <thead className="bg-[#0f0f0f] text-gray-500">
                    <tr>
                      <th className="px-3 py-2 font-medium">{pos === "Overall" ? "Rank" : `${pos} #`}</th>
                      <th className="px-3 py-2 text-center font-medium">
                        <InfoTip label="Tier">{GLOSSARY.tier}</InfoTip>
                      </th>
                      <th className="px-3 py-2 font-medium">Player</th>
                      <th className="px-3 py-2 font-medium">Pos</th>
                      <th className="px-3 py-2 font-medium">Team</th>
                      <th className="px-3 py-2 text-right font-medium">Bye</th>
                      <th className="px-3 py-2 text-right font-medium">G</th>
                      <th className="px-3 py-2 text-right font-medium">Proj pts</th>
                      <th className="px-3 py-2 font-medium">80% range</th>
                      <th className="px-3 py-2 text-right font-medium">
                        <InfoTip label="VOR">{GLOSSARY.vor}</InfoTip>
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
                      {pos === "Overall" && <th className="px-3 py-2 text-right font-medium">Pos rank</th>}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1a1a1a]">
                    {paged.map((p: Player, i: number) => {
                      const rank = rankOf(p, pos)
                      const tier = tierOf.get(p.id) ?? null
                      // a tier boundary is only meaningful between CONSECUTIVE board rows, so it is
                      // suppressed while searching (which removes the rows in between)
                      const startsTier = tier != null && !q.trim() && startsTierAt[i]
                      return (
                        <tr
                          key={p.id}
                          className={`hover:bg-[#0f0f0f] ${
                            startsTier && i > 0 ? "border-t-2 border-t-[#10b981]/30" : ""
                          }`}
                        >
                          <td className="px-3 py-2 font-medium text-gray-500">{rank}</td>
                          <td className="px-3 py-2 text-center">
                            {tier == null ? (
                              <span className="text-[10px] text-gray-700">—</span>
                            ) : startsTier ? (
                              <span className="rounded border border-[#10b981]/40 bg-[#10b981]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[#10b981]">
                                T{tier}
                              </span>
                            ) : (
                              <span className="text-[10px] text-gray-700">{tier}</span>
                            )}
                          </td>
                          <td className="px-3 py-2">
                            <Link
                              href={`/fantasy/player/${p.id}`}
                              className="flex items-center gap-1.5 font-medium text-gray-200 hover:text-[#10b981] hover:underline"
                            >
                              <span>{p.name}</span>
                              {p.rookie && <RookieBadge />}
                            </Link>
                          </td>
                          <td className="px-3 py-2">
                            <PosBadge pos={p.pos} />
                          </td>
                          <td className="px-3 py-2 text-gray-400">{teamLabel(p)}</td>
                          <td className="px-3 py-2 text-right text-gray-500">{p.bye ?? "—"}</td>
                          <td className="px-3 py-2 text-right text-gray-400">{numOrLock(p.g, p.locked)}</td>
                          <td className="px-3 py-2 text-right font-semibold text-gray-100">{numOrLock(p.pts, p.locked)}</td>
                          <td className="w-40 px-3 py-2">
                            {p.locked ? (
                              <LockChip title="Subscribe to unlock the projected range" />
                            ) : p.ptsP10 != null && p.ptsP90 != null && domain ? (
                              <>
                                {/* every rookie's band is class-level (shared across his draft
                                    tier), so it is demoted rather than shown as his own range */}
                                <RangeCell p10={p.ptsP10} p90={p.ptsP90} classLevel={p.rookie} />
                                <IntervalBar
                                  p10={p.ptsP10}
                                  point={p.pts}
                                  p90={p.ptsP90}
                                  min={domain.min}
                                  max={domain.max}
                                  classLevel={p.rookie}
                                />
                              </>
                            ) : (
                              <span className="text-[11px] text-gray-600">—</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-right text-gray-300">{numOrLock(p.vor, p.locked)}</td>
                          {hasAdp && (
                            <>
                              <td className="px-3 py-2 text-right text-gray-400">
                                {p.adp != null ? num(p.adp) : "—"}
                              </td>
                              <td className="px-3 py-2 text-right">
                                <AdpDelta
                                  delta={(() => {
                                    const ref = adpRefOf(p)
                                    return ref != null ? ref - rank : null
                                  })()}
                                />
                              </td>
                            </>
                          )}
                          {pos === "Overall" && (
                            <td className="px-3 py-2 text-right text-gray-500">
                              {p.pos}
                              {p.posRank}
                            </td>
                          )}
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              <div className="mt-3">
                <Pagination
                  page={page}
                  pageSize={pageSize}
                  total={rows.length}
                  onPage={setPage}
                  onPageSize={setPageSize}
                />
              </div>
            </>
          )}

          <div className="mt-6">
            <UncertaintyNote>
              <p className="mt-2">
                <span className="font-semibold text-gray-300">Why the order changes with format.</span>{" "}
                Each board re-scores the same projected stat line under your league&apos;s rules, then
                re-derives replacement level for that roster shape and league size — so superflex lifts
                quarterbacks and full-PPR lifts pass-catchers for a real reason, not a cosmetic tweak.
              </p>
              <p className="mt-2">
                <span className="font-semibold text-gray-300">Kickers and defences.</span> Both are
                ranked here, but off a deliberately base projection: they are the least predictable
                positions in fantasy, and the ordering within them separates good situations from bad
                rather than good players from bad. They are shown without tiers on purpose — the
                whole field fits inside a few points, so any &ldquo;tier break&rdquo; there would be
                splitting noise. Treat that end of the board as streaming options.
              </p>
              {hasAdp && (
                <p className="mt-2">
                  <span className="font-semibold text-gray-300">About the ADP column.</span> ADP is
                  where the public is drafting these players, shown so you can see where our board and
                  the room disagree. We are not claiming our order is the better one — a gap is a
                  prompt to look, and the 80% range next to it tells you how much the model actually
                  knows. Undrafted players show no ADP.
                </p>
              )}
              <MarketLeanNote
                lean={manifest?.projections?.market_lean}
                note={manifest?.projections?.market_lean_note}
              />
            </UncertaintyNote>
          </div>
        </>
      )}
    </div>
  )
}
