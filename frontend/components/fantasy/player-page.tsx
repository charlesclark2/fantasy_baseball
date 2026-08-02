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
//
// 🔓 NF3.2 — SEASON-SCOPED ENTITLEMENT. This route is now reachable with no fantasy entitlement at
// all (the route file dropped `FantasyGuard`). `FantasyPlayerPage` below is a thin DISPATCHER — it
// calls no data hooks of its own beyond `useAuth`, and mounts one of two genuinely separate child
// components based on entitlement, which is what keeps this rules-of-hooks-safe (each child owns its
// own hook call sequence rather than the same component conditionally skipping hooks):
//   • `EntitledPlayerView` — the ENTIRE pre-NF3.2 page, byte-for-byte unchanged, for anyone who
//     already has fantasy access. Nothing about the paying experience changes.
//   • `PublicPlayerView` — identity + past-season track record ONLY, sourced from the PUBLIC
//     `lib/fantasy-track-record.ts` endpoints. It never calls `useFantasyProjections`/
//     `useFantasyBoard` at all (not "calls them and hides the result" — genuinely never invoked), so
//     there is no path by which the current/locked season's projection reaches an unentitled client.

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { ChevronLeft, Lock } from "lucide-react"
import { useAuth } from "@/lib/auth-context"
import { canAccess } from "@/lib/entitlements"
import {
  useFantasyManifest,
  useFantasyProjections,
  useFormatSelection,
  useResolvedBoard,
  useSavedLeagues,
} from "@/lib/fantasy-queries"
import { useAllTrackRecordSeasons, useTrackRecordManifest } from "@/lib/fantasy-track-record"
import { positionTierMap, type Player } from "@/lib/draft-optimizer"
import { initials, nflTeamLogoUrl } from "@/lib/nfl-teams"
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
  PlayerContributionsPanel,
  PosBadge,
  ProvenanceLine,
  RangeCell,
  RookieBadge,
  STAT_COLS,
  UNCERTAINTY_HELP,
  UNCERTAINTY_LABEL,
  MarketLeanNote,
  UncertaintyNote,
  num,
  int,
  teamLabel,
} from "@/components/fantasy/shared"

/** 72 → "72nd", 1 → "1st", 11 → "11th", etc. */
function ordinal(n: number): string {
  const mod100 = n % 100
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`
  switch (n % 10) {
    case 1:
      return `${n}st`
    case 2:
      return `${n}nd`
    case 3:
      return `${n}rd`
    default:
      return `${n}th`
  }
}

/** Where `value` falls in `pool` (both on the same points scale), as a 0–100 percentile. Null if
 *  there's nothing to compare against. */
function percentileRank(value: number | null | undefined, pool: (number | null | undefined)[]): number | null {
  if (value == null) return null
  const values = pool.filter((v): v is number => v != null)
  if (values.length === 0) return null
  const belowOrEqual = values.filter((v) => v <= value).length
  return Math.round((belowOrEqual / values.length) * 100)
}

/** Age as of TODAY, computed on the client from `birthDate` — not baked in server-side, so it
 *  never goes stale between re-exports (a player's age changes daily; the export doesn't). */
function ageFromBirthDate(birthDate: string | null | undefined): number | null {
  if (!birthDate) return null
  const bd = new Date(birthDate)
  if (isNaN(bd.getTime())) return null
  const now = new Date()
  let age = now.getFullYear() - bd.getFullYear()
  const beforeBirthdayThisYear =
    now.getMonth() < bd.getMonth() || (now.getMonth() === bd.getMonth() && now.getDate() < bd.getDate())
  if (beforeBirthdayThisYear) age -= 1
  return age
}

/** 77 → `6'5"` */
function formatHeight(inches: number): string {
  return `${Math.floor(inches / 12)}'${inches % 12}"`
}

/** Stack a Tile's optional sub-lines, dropping falsy parts, without rendering an empty wrapper
 *  when nothing survives. */
function combineSub(...parts: (React.ReactNode | null | undefined | false)[]): React.ReactNode | undefined {
  const present = parts.filter((p): p is React.ReactNode => !!p)
  if (present.length === 0) return undefined
  return (
    <>
      {present.map((p, i) => (
        <div key={i}>{p}</div>
      ))}
    </>
  )
}

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

/** Entry point — see the module docstring for why this is a plain dispatcher with no hooks of its
 *  own besides `useAuth`/`useParams`. */
export function FantasyPlayerPage() {
  const { playerId } = useParams<{ playerId: string }>()
  const { groups, loading: authLoading } = useAuth()
  if (authLoading) return <LoadingBlock label="Loading player…" />
  if (!canAccess("fantasy", groups)) return <PublicPlayerView playerId={playerId} />
  return <EntitledPlayerView playerId={playerId} />
}

function EntitledPlayerView({ playerId }: { playerId: string }) {
  const [logoFailed, setLogoFailed] = useState(false)
  const [photoFailed, setPhotoFailed] = useState(false)
  // Client-side nav between players (Player Search, board links) reuses this component rather than
  // remounting it, so an image-load failure recorded for the PREVIOUS player must not carry over.
  useEffect(() => {
    setLogoFailed(false)
    setPhotoFailed(false)
  }, [playerId])

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

  // WHY a player has no tier — a bare "—" with no explanation reads as a bug. Only two things ever
  // suppress a tier (see positionTierMap): the position is deliberately never tiered (K/DST — the
  // whole field is noise-flat), or the player is at/below his format's replacement level (only
  // above-replacement rows are tiered — see league-board.tsx's identical rule). Below-replacement is
  // format-DEPENDENT: a QB with no tier in a 1-QB league can easily tier in superflex.
  const tierReason = useMemo(() => {
    if (!proj || tier != null) return null
    if (LOW_PREDICTABILITY_POSITIONS.includes(proj.pos)) {
      return "Kickers and defenses aren't tiered — the whole position fits inside a few points, so a tier break there would be splitting noise, not signal."
    }
    if (boardRow) {
      return `Below replacement level in ${config?.label ?? "this format"} (VOR ${num(boardRow.vor)}) — only above-replacement players are tiered, since a break below replacement isn't a meaningful draft signal. Try a format where he starts more often (e.g. superflex for a QB).`
    }
    return null
  }, [proj, tier, boardRow, config])

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

  // Percentile within position: how this projection stacks up against every OTHER currently-
  // projected player at the same position — the reference-scoring columns compare against the full
  // projections pool (format-independent), the league column against this format's own board.
  const posProjPool = useMemo(() => {
    if (!proj) return { std: [], half: [], ppr: [] }
    const rows = (projPayload?.players ?? []).filter((p) => p.pos === proj.pos)
    return { std: rows.map((p) => p.fpStd), half: rows.map((p) => p.fpHalf), ppr: rows.map((p) => p.fpPpr) }
  }, [proj, projPayload])
  const posBoardPool = useMemo(
    () => (proj ? (board ?? []).filter((p) => p.pos === proj.pos).map((p) => p.pts) : []),
    [proj, board],
  )
  const pctStd = proj ? percentileRank(proj.fpStd, posProjPool.std) : null
  const pctHalf = proj ? percentileRank(proj.fpHalf, posProjPool.half) : null
  const pctPpr = proj ? percentileRank(proj.fpPpr, posProjPool.ppr) : null
  const pctLeague = proj && boardRow ? percentileRank(boardRow.pts, posBoardPool) : null

  const teamAbbrev = proj?.team ?? null
  const logoUrl = !logoFailed ? nflTeamLogoUrl(teamAbbrev) : null
  const photoUrl = proj?.headshot && !photoFailed ? proj.headshot : null
  const age = ageFromBirthDate(proj?.birthDate)

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
            <div className="flex items-start gap-4">
              {/* An official nfl.com headshot (nflverse's identity table, ~99% coverage among
                  active players) when the export carries one; initials otherwise — e.g. a very
                  recent addition the source hasn't caught up to yet, or the image URL 404s. */}
              <div className="relative h-16 w-16 flex-shrink-0">
                {photoUrl ? (
                  <img
                    src={photoUrl}
                    alt={proj.name}
                    className="h-16 w-16 rounded-full border-2 border-[#262626] bg-[#1a1a1a] object-cover"
                    onError={() => setPhotoFailed(true)}
                  />
                ) : (
                  <div className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-full border-2 border-[#262626] bg-[#1a1a1a] text-lg font-bold text-gray-500">
                    {initials(proj.name)}
                  </div>
                )}
                {logoUrl && (
                  <img
                    src={logoUrl}
                    alt={teamAbbrev ?? "team logo"}
                    className="absolute -bottom-1 -right-1 h-7 w-7 rounded-full border-2 border-[#0a0a0a] bg-[#111111] object-contain p-0.5"
                    onError={() => setLogoFailed(true)}
                  />
                )}
              </div>
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

          {/* Bio — absent entirely for a DST (a team, not a person) or if the source has nothing
              for this player yet; never rendered as a row of dashes. */}
          {(age != null || proj.heightIn != null || proj.weightLb != null || proj.college || proj.yearsExp != null) && (
            <section className="mb-6">
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
                Player Info
              </h2>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
                <Tile label="Age" value={age != null ? String(age) : "—"} />
                <Tile label="Height" value={proj.heightIn != null ? formatHeight(proj.heightIn) : "—"} />
                <Tile label="Weight" value={proj.weightLb != null ? `${proj.weightLb} lbs` : "—"} />
                <Tile label="College" value={proj.college ?? "—"} />
                <Tile
                  label="NFL Exp."
                  value={proj.yearsExp != null ? `${proj.yearsExp} yr${proj.yearsExp === 1 ? "" : "s"}` : "—"}
                />
              </div>
            </section>
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
              <Tile
                label="Standard"
                value={num(proj.fpStd)}
                sub={combineSub(pctStd != null && `${ordinal(pctStd)} pct. among ${proj.pos}s`)}
              />
              <Tile
                label="Half PPR"
                value={num(proj.fpHalf)}
                sub={combineSub(pctHalf != null && `${ordinal(pctHalf)} pct. among ${proj.pos}s`)}
              />
              <Tile
                label="Full PPR (reference)"
                value={num(proj.fpPpr)}
                sub={combineSub(
                  pctPpr != null && `${ordinal(pctPpr)} pct. among ${proj.pos}s`,
                  proj.fpP10 != null && proj.fpP90 != null && `80%: ${int(proj.fpP10)}–${int(proj.fpP90)}`,
                )}
              />
              <Tile
                label={config ? `${config.label} (your league)` : "Your league"}
                value={boardLoading ? "…" : boardRow?.pts != null ? num(boardRow.pts) : "—"}
                sub={
                  !boardLoading && boardRow?.pts == null
                    ? "Not ranked in this format"
                    : combineSub(
                        pctLeague != null && `${ordinal(pctLeague)} pct. among ${proj.pos}s`,
                        boardRow?.ptsP10 != null &&
                          boardRow?.ptsP90 != null &&
                          `80%: ${int(boardRow.ptsP10)}–${int(boardRow.ptsP90)}`,
                      )
                }
                emphasis
              />
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-gray-600">
              Standard / Half PPR / Full PPR are a fixed reference scoring, independent of your
              league&apos;s actual rules. The last card is this player re-scored under your selected
              league&apos;s exact format and roster shape. &ldquo;Pct.&rdquo; is where this projection
              ranks among every currently-projected player at his position — not his league board rank.
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
                  <Tile
                    label={<InfoTip label="Overall Rank">{GLOSSARY.overallRank}</InfoTip>}
                    value={`#${boardRow.ovrRank}`}
                  />
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
                    sub={tierReason}
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

          {/* NF3.4 — what pushes THIS player's number up or down (a separate research-model read) */}
          <PlayerContributionsPanel
            playerName={proj.name}
            contrib={proj.contrib}
            legend={manifest?.featureLegend}
          />

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
            {/* Scoped to THIS player's own position — the page renders one player, so listing every
                market-leaning position on the board would be noise he has to filter himself. */}
            <MarketLeanNote
              lean={proj.mktLean ? { [proj.pos]: proj.mktLean } : null}
              note={projPayload?.market_lean_note}
            />
          </UncertaintyNote>
        </>
      )}
    </div>
  )
}

/** NF3.2 — the PUBLIC half of the split: identity + past-season track record only, for a visitor
 *  with no fantasy entitlement. Sourced ENTIRELY from `lib/fantasy-track-record.ts`'s public
 *  endpoints — never `useFantasyProjections`/`useResolvedBoard` (those stay unused in this
 *  component's whole body, not merely unrendered). The current/locked season renders as a static
 *  upsell card, never a fetched-then-hidden number. */
function PublicPlayerView({ playerId }: { playerId: string }) {
  const { data: manifest, isLoading: manifestLoading } = useTrackRecordManifest()
  const seasons = manifest?.seasons ?? []
  const { rows, isLoading: rowsLoading } = useAllTrackRecordSeasons(seasons)
  const playerRows = useMemo(
    () => rows.filter((r) => r.playerId === playerId).sort((a, b) => b.season - a.season),
    [rows, playerId],
  )
  const identity = playerRows[0]
  const loading = manifestLoading || (seasons.length > 0 && rowsLoading)
  const lockedSeason = manifest?.lockedSeason ?? 2026

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <Link
        href="/fantasy/track-record"
        className="mb-5 inline-flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
      >
        <ChevronLeft className="h-3.5 w-3.5" />
        Track Record
      </Link>

      {loading && <LoadingBlock label="Loading player…" />}

      {!loading && !identity && (
        <EmptyBlock
          title="Player not found"
          detail="This player doesn't appear in the published past-season track record — the export may not include him, or the link is out of date."
        />
      )}

      {identity && (
        <>
          <div className="mb-6 flex items-center gap-4">
            <div className="flex h-16 w-16 flex-shrink-0 items-center justify-center overflow-hidden rounded-full border-2 border-[#262626] bg-[#1a1a1a] text-lg font-bold text-gray-500">
              {initials(identity.playerName)}
            </div>
            <div>
              <h1 className="text-3xl font-bold text-white">{identity.playerName}</h1>
              <p className="mt-1">
                <PosBadge pos={identity.position} />
              </p>
            </div>
          </div>

          <section className="mb-6">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
              Past-season track record
            </h2>
            <div className="overflow-x-auto rounded-lg border border-[#262626] bg-[#0f0f0f]">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#262626] text-[10px] uppercase tracking-wider text-gray-500">
                    <th className="px-3 py-2">Season</th>
                    <th className="px-3 py-2 text-right">Our rank</th>
                    <th className="px-3 py-2 text-right">ADP rank</th>
                    <th className="px-3 py-2 text-right">Actual rank</th>
                    <th className="px-3 py-2 text-right">Actual pts</th>
                    <th className="px-3 py-2">
                      <InfoTip label="Fade">{GLOSSARY.fade}</InfoTip>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {playerRows.map((r) => (
                    <tr key={r.season} className="border-b border-[#1a1a1a] last:border-0">
                      <td className="px-3 py-2 text-gray-200">{r.season}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-300">{r.ourRank}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-300">{int(r.adpRank)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-300">{r.actualRank}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-400">
                        {num(r.actualPoints)}
                      </td>
                      <td className="px-3 py-2">
                        {r.isFade && (
                          <span className="rounded border border-[#10b981]/40 bg-[#10b981]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[#10b981]">
                            fade
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <div className="rounded-lg border border-[#262626] bg-[#111111] p-4 text-center">
            <p className="mb-2 text-sm text-gray-300">
              Want his {lockedSeason} projection, 80% range, and league-scored rank?
            </p>
            <Link
              href="/subscribe"
              className="inline-flex items-center gap-1.5 rounded border border-[#10b981]/40 bg-[#10b981]/10 px-3 py-1.5 text-xs font-semibold text-[#10b981] transition-colors hover:bg-[#10b981]/20"
            >
              <Lock className="h-3 w-3" /> Unlock {lockedSeason} projections
            </Link>
          </div>
        </>
      )}
    </div>
  )
}
