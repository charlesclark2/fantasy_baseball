"use client"

// NF3.1 — the per-player drill-down. Every NF3 board row (Projections, Rankings, League Board,
// Draft Optimizer) links here. It is a CLIENT-SIDE JOIN across the two blobs those surfaces already
// fetch — the format-independent season projection (raw stat line + the honest uncertainty
// metadata) and the currently-selected league's scored board (points/VOR/rank/ADP for THIS format)
// — so no new endpoint is needed (NF3.1: "add a route only if the client join gets ugly").
//
// 🔒 HONEST (NF-D3 / best_alpha=0): a projection and transparency page. No "beats consensus" framing
// — ADP is a neutral reference, and the 80% range is drawn so the uncertainty is never hidden behind
// a single number.

import { useMemo } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { ChevronLeft } from "lucide-react"
import {
  useFantasyManifest,
  useFantasyProjections,
  useFormatSelection,
  useResolvedBoard,
  useSavedLeagues,
} from "@/lib/fantasy-queries"
import { positionTierMap, type Player } from "@/lib/draft-optimizer"
import type { ProjectedPlayer } from "@/lib/fantasy"
import {
  ADP_DELTA_LABEL,
  AdpDelta,
  ALL_POSITIONS,
  ConfidenceBadge,
  EmptyBlock,
  FormatSelector,
  GLOSSARY,
  InfoTip,
  IntervalBar,
  LoadingBlock,
  LOW_PREDICTABILITY_POSITIONS,
  PosBadge,
  ProvenanceLine,
  RangeCell,
  RookieBadge,
  STAT_COLS,
  UNCERTAINTY_HELP,
  UNCERTAINTY_LABEL,
  UncertaintyNote,
  num,
  int,
  teamLabel,
} from "@/components/fantasy/shared"

function Tile({
  label,
  value,
  sub,
  emphasis = false,
}: {
  label: React.ReactNode
  value: React.ReactNode
  sub?: React.ReactNode
  emphasis?: boolean
}) {
  return (
    <div className="rounded-lg border border-[#262626] bg-[#111111] px-4 py-3">
      <div className="text-[11px] font-medium uppercase tracking-wider text-gray-500">{label}</div>
      <div className={`mt-1 tabular-nums ${emphasis ? "text-2xl font-bold text-white" : "text-lg font-semibold text-gray-100"}`}>
        {value}
      </div>
      {sub && <div className="mt-1 text-[11px] text-gray-500">{sub}</div>}
    </div>
  )
}

export function FantasyPlayerPage() {
  const { playerId } = useParams<{ playerId: string }>()

  const { data: projPayload, isLoading: projLoading, error: projError } = useFantasyProjections()
  const { data: manifest } = useFantasyManifest()
  const { data: savedLeagues } = useSavedLeagues()
  const { configName, size, setConfigName, setSize } = useFormatSelection(manifest, savedLeagues)
  const { board, isLoading: boardLoading } = useResolvedBoard(configName, size)

  const config = manifest?.configs.find((c) => c.name === configName)

  const proj: ProjectedPlayer | undefined = useMemo(
    () => projPayload?.players.find((p) => p.id === playerId),
    [projPayload, playerId],
  )
  const boardRow: Player | undefined = useMemo(
    () => (board ?? []).find((p) => p.id === playerId),
    [board, playerId],
  )

  // Position tier, computed the SAME way Rankings does it: above-replacement rows at this player's
  // position only, ranked on league points — never the whole (noisy, long-tailed) board. K/DST are
  // deliberately left untiered (see LOW_PREDICTABILITY_POSITIONS in shared.tsx).
  const tier = useMemo(() => {
    if (!proj || !board || LOW_PREDICTABILITY_POSITIONS.includes(proj.pos)) return null
    const posRows = board.filter(
      (p) => p.pos === proj.pos && p.pts != null && (ALL_POSITIONS as readonly string[]).includes(p.pos),
    )
    const m = positionTierMap(posRows, (p) => p.pts ?? -Infinity, LOW_PREDICTABILITY_POSITIONS)
    return m.get(proj.id) ?? null
  }, [proj, board])

  // Same scale Rankings' Overall tab compares ADP against — both are overall pick numbers.
  const adpDelta =
    boardRow?.adp != null && boardRow?.ovrRank != null ? boardRow.adp - boardRow.ovrRank : null

  const statCols = proj ? STAT_COLS[proj.pos] ?? [] : []
  // The interval carried in the projections payload is on the PPR total only; once the board for
  // this league is loaded, its league-points range is the more relevant one to draw.
  const rangeP10 = boardRow?.ptsP10 ?? proj?.fpP10 ?? null
  const rangeP90 = boardRow?.ptsP90 ?? proj?.fpP90 ?? null
  const rangePoint = boardRow?.pts ?? proj?.fpPpr ?? null

  // ⚠️ The bar's domain must NOT be the player's own [p10, p90] — that draws his band across the
  // FULL width every time (a solid line, uninformative regardless of whether his range is narrow
  // or wide relative to his position). The domain is his position's realistic spread instead — the
  // widest band any player at his position carries in the same source (board points once loaded,
  // else the reference PPR projection), floored at 0 since fantasy points can't go negative — so
  // the drawn band shows where THIS player sits (and how wide he is) relative to his peers.
  const rangeDomain = useMemo(() => {
    if (!proj) return null
    if (boardRow?.ptsP10 != null && board) {
      let max = -Infinity
      for (const p of board) if (p.pos === proj.pos && p.ptsP90 != null) max = Math.max(max, p.ptsP90)
      if (Number.isFinite(max) && max > 0) return { min: 0, max }
    }
    let max = -Infinity
    for (const p of projPayload?.players ?? []) if (p.pos === proj.pos && p.fpP90 != null) max = Math.max(max, p.fpP90)
    if (Number.isFinite(max) && max > 0) return { min: 0, max }
    return rangeP10 != null && rangeP90 != null ? { min: rangeP10, max: rangeP90 } : null
  }, [proj, boardRow, board, projPayload, rangeP10, rangeP90])
  // Per-player vs class-level is a property of the MODEL (uncType, NF1.7), never of the raw
  // `rookie` flag — a rookie's band is per-player unless it fell back to the thin-history class
  // bucket. Mislabelling a per-player NF1.7 band "Class-level" is exactly what this story forbids.
  const classLevel = proj?.uncType === "calibrated"

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <Link
        href="/fantasy/players"
        className="mb-5 inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
      >
        <ChevronLeft className="h-3.5 w-3.5" />
        Player Search
      </Link>

      {projLoading && <LoadingBlock label="Loading player…" />}

      {!projLoading && (projError || !proj) && (
        <EmptyBlock
          title="Player not found"
          detail="This player isn't in the current season projections — the export may not include him, or the link is out of date."
        />
      )}

      {proj && (
        <>
          {/* Header */}
          <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-3xl font-bold text-white">{proj.name}</h1>
                {proj.rookie && <RookieBadge />}
              </div>
              <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-gray-500">
                <PosBadge pos={proj.pos} />
                <span>{teamLabel(proj)}</span>
                {proj.bye != null && <span>· Bye {proj.bye}</span>}
                {proj.rookie && proj.draftPick != null && <span>· Draft pick {proj.draftPick}</span>}
                <span className="inline-flex items-center gap-1">
                  · <InfoTip label="Confidence">{GLOSSARY.confidence}</InfoTip>
                  <ConfidenceBadge conf={proj.conf} />
                </span>
              </p>
            </div>
            <ProvenanceLine
              season={projPayload?.season ?? 2026}
              generatedAt={projPayload?.generated_at}
              extra={projPayload?.base_season ? `built off ${projPayload.base_season} production` : null}
            />
          </div>

          {proj.lowPred && (
            <div className="mb-6 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs leading-relaxed text-amber-200">
              {proj.predNote ??
                "This position's projection is deliberately a base one — read it as a streaming tier, not a precise rank."}
            </div>
          )}

          {/* League format context */}
          <div className="mb-6 rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
            <h2 className="mb-2 text-sm font-semibold text-gray-200">Your league</h2>
            <p className="mb-3 text-xs leading-relaxed text-gray-500">
              The points, value and rank below are scored for the league format selected here — the
              same selection Rankings and the League Board use, and it stays in sync between them.
            </p>
            <FormatSelector
              manifest={manifest}
              configName={configName}
              size={size}
              onConfig={setConfigName}
              onSize={setSize}
              savedLeagues={savedLeagues}
            />
          </div>

          {/* Fantasy points, side by side */}
          <section className="mb-6">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
              Fantasy points
            </h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Tile label="Standard" value={num(proj.fpStd)} />
              <Tile label="Half PPR" value={num(proj.fpHalf)} />
              <Tile
                label="Full PPR (reference)"
                value={num(proj.fpPpr)}
                sub={
                  proj.fpP10 != null && proj.fpP90 != null
                    ? `80%: ${int(proj.fpP10)}–${int(proj.fpP90)}`
                    : undefined
                }
              />
              <Tile
                label={config ? `${config.label} (your league)` : "Your league"}
                value={boardLoading ? "…" : boardRow?.pts != null ? num(boardRow.pts) : "—"}
                sub={
                  !boardLoading && boardRow?.pts == null
                    ? "Not ranked in this format"
                    : boardRow?.ptsP10 != null && boardRow?.ptsP90 != null
                      ? `80%: ${int(boardRow.ptsP10)}–${int(boardRow.ptsP90)}`
                      : undefined
                }
                emphasis
              />
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-gray-600">
              Standard / Half PPR / Full PPR are a fixed reference scoring, independent of your
              league&apos;s actual rules. The last card is this player re-scored under your selected
              league&apos;s exact format and roster shape.
            </p>
          </section>

          {/* 80% range, drawn */}
          <section className="mb-6 rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                80% range
              </h2>
              <span
                className="text-[10px] uppercase tracking-wide text-gray-500"
                title={proj.uncType ? UNCERTAINTY_HELP[proj.uncType] : undefined}
              >
                {proj.uncType ? UNCERTAINTY_LABEL[proj.uncType] ?? proj.uncType : "—"}
              </span>
            </div>
            {rangeP10 != null && rangeP90 != null && rangeDomain ? (
              <>
                <IntervalBar
                  p10={rangeP10}
                  point={rangePoint}
                  p90={rangeP90}
                  min={rangeDomain.min}
                  max={rangeDomain.max}
                  classLevel={classLevel}
                />
                <div className="mt-2 flex items-center justify-between">
                  <RangeCell p10={rangeP10} p90={rangeP90} classLevel={classLevel} />
                  <span className="text-[10px] text-gray-600">
                    vs. {proj.pos} field: 0–{int(rangeDomain.max)}
                  </span>
                </div>
              </>
            ) : (
              <p className="text-xs text-gray-600">No range available yet for this player.</p>
            )}
            <p className="mt-3 text-[11px] leading-relaxed text-gray-500">
              {proj.uncType ? UNCERTAINTY_HELP[proj.uncType] : null}
            </p>
          </section>

          {/* Draft value: VOR / rank / tier / ADP */}
          <section className="mb-6">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
              Draft value — {config?.label ?? "your league"}
            </h2>
            {boardLoading && <LoadingBlock label="Scoring the board…" />}
            {!boardLoading && !boardRow && (
              <EmptyBlock
                title="Not ranked in this format"
                detail="This player doesn't have a published board row for the selected league format and size — try another format above, or check Rankings once it's published."
              />
            )}
            {!boardLoading && boardRow && (
              <>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <Tile
                    label={<InfoTip label="VOR">{GLOSSARY.vor}</InfoTip>}
                    value={num(boardRow.vor)}
                    sub={
                      boardRow.vorP10 != null && boardRow.vorP90 != null
                        ? `80%: ${int(boardRow.vorP10)}–${int(boardRow.vorP90)}`
                        : undefined
                    }
                  />
                  <Tile label="Position rank" value={`${proj.pos}${boardRow.posRank}`} />
                  <Tile label="Overall rank" value={`#${boardRow.ovrRank}`} />
                  <Tile
                    label={<InfoTip label="Tier">{GLOSSARY.tier}</InfoTip>}
                    value={
                      tier != null ? (
                        <span className="rounded border border-[#10b981]/40 bg-[#10b981]/10 px-1.5 py-0.5 text-base font-semibold text-[#10b981]">
                          T{tier}
                        </span>
                      ) : (
                        "—"
                      )
                    }
                    sub={
                      tier == null && LOW_PREDICTABILITY_POSITIONS.includes(proj.pos)
                        ? "Kickers and defenses aren't tiered — see below"
                        : undefined
                    }
                  />
                </div>
                {boardRow.adp != null && (
                  <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <Tile
                      label={
                        <InfoTip label="ADP">
                          {GLOSSARY.adp}
                          {config?.adpFormat ? ` Sample: ${config.adpFormat}, ${size}-team.` : ""}
                        </InfoTip>
                      }
                      value={num(boardRow.adp)}
                    />
                    <Tile
                      label={<InfoTip label={ADP_DELTA_LABEL}>{GLOSSARY.adpDelta}</InfoTip>}
                      value={<AdpDelta delta={adpDelta} />}
                    />
                  </div>
                )}
              </>
            )}
          </section>

          {/* Raw season stat line */}
          {statCols.length > 0 && (
            <section className="mb-6">
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
                2026 season projection
                {proj.g != null ? ` · ${num(proj.g, 0)} games` : ""}
              </h2>
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
                {statCols.map((c) => (
                  <Tile
                    key={String(c.key)}
                    label={c.label}
                    value={num(proj[c.key] as number | null, c.nd ?? 1)}
                  />
                ))}
              </div>
            </section>
          )}

          <UncertaintyNote>
            <p className="mt-2">{UNCERTAINTY_HELP.empirical} {UNCERTAINTY_HELP.calibrated_per_player}</p>
          </UncertaintyNote>
        </>
      )}
    </div>
  )
}
