"use client"

import Link from "next/link"
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ArrowRight, Info } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cdnFetch } from "@/lib/api"
import { nflTeamLogoUrl } from "@/lib/nfl-teams"
import { DISAGREEMENT_HOOK } from "@/lib/fantasy-claim-copy"
import { FANTASY_PROOF as COPY } from "@/lib/home-copy"

/**
 * E9.46 — the FANTASY PRODUCT PROOF, and the first substantive demonstration on the home page.
 *
 * ══ WHAT MAKES THIS HONEST ════════════════════════════════════════════════════════════════════
 *
 * Every number here is read from `/fantasy/nfl/featured-player`, which computes its choice from the
 * served 2026 artifact on each request: of draftable players carrying driver data, the largest gap
 * between our within-position rank and the market's. Nobody curates it, and it is NOT constrained
 * to a player we like more than the crowd — the live selection today is a player we rank *lower*
 * than the market drafts him, and the card renders that direction just as plainly.
 *
 * ⛔ THE LEAN CAVEAT IS NOT DECORATION. Measured on the live artifact: zero of the 111 eligible
 * players have `mktLean == "independent"`, because that value is precisely the thin-data rookie
 * case that carries no drivers. So at every position we could feature, our ranking already blends
 * market consensus — the gap is a real disagreement but never an independent one. A card showing
 * the gap without saying so would overstate it, which is why `leanNote` renders inline and not
 * behind a disclosure.
 *
 * ⭐ THE FORMAT ROW IS THE PERSONALISATION PROOF. "Built for your league, not a generic one" is a
 * claim until a visitor sees ONE player's season total move across standard / half-PPR / full-PPR,
 * at which point it is an observation — and it costs no extra data, since all three scorings are
 * already on the record.
 */

type FeaturedFantasyPlayer = {
  season: number | null
  player: {
    id: string
    name: string
    pos: string
    team: string | null
    bye: number | null
    headshot: string | null
  }
  projection: {
    ptsStd: number | null
    ptsHalf: number | null
    ptsPpr: number | null
    p10: number | null
    p90: number | null
    games: number | null
    conf: string | null
  }
  market: {
    adp: number | null
    adpFormat: string | null
    adpTeams: number | null
    adpRank: number | null
    /** ⭐ E9.46 follow-up — the FULL-BOARD within-position rank, i.e. the number `/fantasy/rankings`
     *  shows for this player. */
    ourRank: number | null
    /** …and our rank among the players the market has actually drafted, which is the population the
     *  gap below is computed in. OPTIONAL: the API Lambda ships only via `deploy.sh` while this
     *  frontend auto-deploys, so there is a guaranteed window where the deployed API does not send
     *  it (NF-C0). Absent ⇒ the reconciliation line simply does not render. */
    ourRankAmongDrafted?: number | null
    rankGap: number | null
  }
  drivers: { feature: string; label: string; pts: number | null }[]
  lean: string | null
  leanNote: string | null
}

const num = (v: number | null | undefined, nd = 1) =>
  v == null ? "—" : v.toLocaleString(undefined, { minimumFractionDigits: nd, maximumFractionDigits: nd })

function PositionRank({ label, pos, rank }: { label: string; pos: string; rank: number | null }) {
  return (
    <div className="rounded-lg border border-[#262626] bg-[#0a0a0a] px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-gray-500">{label}</div>
      <div className="font-mono text-lg font-bold text-white">
        {rank == null ? "—" : `${pos}${rank}`}
      </div>
    </div>
  )
}

export function FeaturedFantasyPlayer() {
  const [photoFailed, setPhotoFailed] = useState(false)
  const { data, isLoading, isError } = useQuery<FeaturedFantasyPlayer>({
    queryKey: ["home", "featured-fantasy-player"],
    // G100-D1 — through our own CDN, not the API Lambda. This read carries NO token and every
    // visitor receives the identical payload, so it is cacheable once for everybody; leaving it on
    // `apiFetch` would put one API Gateway request and one Lambda invocation back on every view of
    // the highest-traffic anonymous page in the product, directly undoing what G100-D1 shipped for
    // the pick card sitting right below this one.
    queryFn: () => cdnFetch("/api/public/featured-player"),
    staleTime: 15 * 60 * 1000,
    retry: 1,
  })

  // ⚠️ The section HIDES on failure rather than rendering a broken card — but the hero and the MLB
  // proof are independent of this read, so the page is never left blank (the AC). Deliberately
  // different from the MLB block, which must always render something: this one is a demonstration
  // of a product whose real surface is one click away, so a skeleton that never resolves would be
  // worse than a clean absence.
  if (isError) return null

  if (isLoading || !data) {
    return (
      <section className="border-t border-[#262626] py-16 md:py-20">
        <div className="mx-auto max-w-3xl px-4">
          <div className="h-4 w-56 animate-pulse rounded bg-[#1c1c1c]" />
          <div className="mt-6 h-64 w-full animate-pulse rounded-xl bg-[#141414]" />
        </div>
      </section>
    )
  }

  const { player, projection, market, drivers } = data
  const logo = nflTeamLogoUrl(player.team)
  const gap = market.rankGap
  // Positive ⇒ we rank him higher than the market drafts him. Both directions are real results and
  // the card states which one this is in words — a coloured arrow alone would read as a verdict.
  const weAreHigher = gap != null && gap > 0
  const gapPhrase =
    gap == null || gap === 0
      ? "We and the market land in the same place on him."
      : weAreHigher
        ? `We rank him ${Math.abs(gap)} ${Math.abs(gap) === 1 ? "spot" : "spots"} higher than the market drafts him.`
        : `We rank him ${Math.abs(gap)} ${Math.abs(gap) === 1 ? "spot" : "spots"} lower than the market drafts him.`

  // ⭐ E9.46 FOLLOW-UP — THE RECONCILIATION LINE, and it exists because two tiles invite subtraction.
  //
  // "Our rank" is now the FULL-BOARD rank, so it agrees with `/fantasy/rankings` when the reader
  // clicks through. "Market rank" can only ever be among the players the market has drafted — the
  // market produces no rank for a player nobody drafts. So the two tiles are on DIFFERENT
  // populations, the gap is computed on the market's one, and a reader who subtracts the tiles
  // arrives at a third number.
  //
  // ⛔ The alternatives were worse. Showing the matched rank in the tile puts a number on the card
  // that the rankings page contradicts (the defect being fixed). Computing the gap across the two
  // populations reports a difference of populations as a disagreement about a player. Saying it
  // outright, only when the two actually differ, costs one line and is the only reading that is true.
  const draftedRank = market.ourRankAmongDrafted ?? null
  const populationNote =
    draftedRank != null && market.ourRank != null && draftedRank !== market.ourRank
      ? `Our rank is his place on our whole board for the position. Among the ${player.pos}s the market actually drafts he is ${player.pos}${draftedRank}, which is the comparison above.`
      : null

  const formats: { label: string; pts: number | null }[] = [
    { label: "Standard", pts: projection.ptsStd },
    { label: "Half-PPR", pts: projection.ptsHalf },
    { label: "Full-PPR", pts: projection.ptsPpr },
  ]

  return (
    <section id="fantasy-proof" className="scroll-mt-20 border-t border-[#262626] py-16 md:py-24">
      <div className="mx-auto max-w-3xl px-4">
        <p className="text-xs font-semibold uppercase tracking-widest text-[#10b981]">
          {COPY.eyebrow}
        </p>
        <h2 className="mt-3 text-balance text-2xl font-bold text-white md:text-3xl">
          {COPY.heading}
        </h2>
        {/* ⭐ NF-TR1's canonical consensus hook, rendered VERBATIM. This section is that sentence
            instantiated — the player we rank furthest from where the crowd drafts him, with the
            drivers behind it — so paraphrasing it here would be the drift `fantasy-claim-copy.ts`
            exists to prevent. It is a content hook, true whichever side of the gap we land on,
            never a superiority claim. */}
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-gray-300">{DISAGREEMENT_HOOK}</p>
        <p className="mt-2 max-w-2xl text-xs leading-relaxed text-gray-500">{COPY.selectionNote}</p>

        <div
          className="mt-8 overflow-hidden rounded-xl border border-[#262626] bg-[#141414] shadow-xl shadow-black/40"
          style={{ borderLeft: "3px solid #10b981" }}
        >
          {/* ── Identity ─────────────────────────────────────────────────────────────────── */}
          <div className="flex items-center gap-4 border-b border-[#262626] p-5 md:p-6">
            {/* ⚠️ THE FALLBACK IS NOT THE FIX, AND ON ITS OWN IT IS A LIABILITY.
                A headshot can fail for two very different reasons: the player genuinely has no
                photo (a recent addition nflverse has not caught up to), or the browser REFUSED the
                load. Initials are right for the first and hide the second — which is exactly how
                `static.www.nfl.com` stayed missing from the CSP `img-src` allowlist unnoticed:
                `player-page.tsx` has this same fallback, so every blocked headshot in the product
                presented as "no photo available" rather than as a defect.
                ⇒ it ships PAIRED with `test_e9_46_image_hosts_are_allowlisted.py`, which asserts
                every image host in the published fixtures is permitted. Do not keep one without
                the other: alone, the fallback makes the next missing host invisible again. */}
            {player.headshot && !photoFailed ? (
              // eslint-disable-next-line @next/next/no-img-element -- the NFL CDN returns a
              // transformed asset per URL; next/image would re-proxy it for no benefit and needs a
              // remotePattern entry. `player-page.tsx` renders the same source the same way.
              <img
                src={player.headshot}
                alt=""
                aria-hidden="true"
                width={64}
                height={64}
                loading="lazy"
                onError={() => setPhotoFailed(true)}
                className="h-16 w-16 shrink-0 rounded-full bg-[#0a0a0a] object-cover ring-1 ring-[#262626]"
              />
            ) : (
              <div
                aria-hidden="true"
                className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-[#0a0a0a] text-lg font-semibold text-gray-500 ring-1 ring-[#262626]"
              >
                {player.name.split(" ").slice(0, 2).map((part) => part[0]).join("")}
              </div>
            )}
            <div className="min-w-0 flex-1">
              <h3 className="truncate text-2xl font-bold text-white md:text-3xl">{player.name}</h3>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-gray-400">
                {logo && (
                  // eslint-disable-next-line @next/next/no-img-element -- see above
                  <img src={logo} alt="" aria-hidden="true" width={18} height={18} className="h-[18px] w-[18px]" />
                )}
                <span className="font-medium text-gray-300">{player.pos}</span>
                <span aria-hidden="true">·</span>
                <span>{player.team}</span>
                {player.bye != null && (
                  <>
                    <span aria-hidden="true">·</span>
                    <span className="text-gray-500">Bye {player.bye}</span>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* ── The disagreement ─────────────────────────────────────────────────────────── */}
          <div className="border-b border-[#262626] p-5 md:p-6">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <PositionRank label={COPY.ourRankLabel} pos={player.pos} rank={market.ourRank} />
              <PositionRank label={COPY.marketRankLabel} pos={player.pos} rank={market.adpRank} />
              <div className="rounded-lg border border-[#262626] bg-[#0a0a0a] px-3 py-2">
                <div className="text-[10px] uppercase tracking-wider text-gray-500">
                  {COPY.adpLabel}
                </div>
                <div className="font-mono text-lg font-bold text-gray-300">
                  {num(market.adp, 1)}
                </div>
              </div>
              <div className="rounded-lg border border-[#262626] bg-[#0a0a0a] px-3 py-2">
                <div className="text-[10px] uppercase tracking-wider text-gray-500">
                  {COPY.gamesLabel}
                </div>
                <div className="font-mono text-lg font-bold text-gray-300">
                  {num(projection.games, 1)}
                </div>
              </div>
            </div>

            <p className="mt-4 text-sm font-medium text-white">{gapPhrase}</p>

            {populationNote && (
              <p className="mt-2 text-xs leading-relaxed text-gray-500" data-testid="rank-population-note">
                {populationNote}
              </p>
            )}

            {/* ⛔ The caveat renders WITH the gap, not behind a disclosure. */}
            {data.leanNote && (
              <p className="mt-2 text-xs leading-relaxed text-gray-500">
                {data.lean && (
                  <span className="mr-1 rounded bg-[#1a1a1a] px-1.5 py-0.5 font-mono text-[10px] text-gray-400">
                    {data.lean}
                  </span>
                )}
                {data.leanNote}
              </p>
            )}
          </div>

          {/* ── The projection + its range ───────────────────────────────────────────────── */}
          <div className="border-b border-[#262626] p-5 md:p-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <div className="text-[10px] uppercase tracking-wider text-gray-500">
                  Expected pts · Full-PPR
                </div>
                <div className="font-mono text-4xl font-bold text-[#10b981]">
                  {num(projection.ptsPpr, 1)}
                </div>
              </div>
              <div className="text-right">
                <div className="text-[10px] uppercase tracking-wider text-gray-500">
                  {COPY.rangeLabel}
                </div>
                <div className="font-mono text-lg text-gray-300">
                  {num(projection.p10, 0)} – {num(projection.p90, 0)}
                </div>
              </div>
            </div>
            <p className="mt-3 text-xs leading-relaxed text-gray-500">{COPY.gamesNote}</p>
          </div>

          {/* ── Personalisation: one player, three formats ───────────────────────────────── */}
          <div className="border-b border-[#262626] p-5 md:p-6">
            <div className="text-xs font-semibold uppercase tracking-wider text-gray-400">
              {COPY.formatsHeading}
            </div>
            <div className="mt-3 grid grid-cols-3 gap-3">
              {formats.map((f) => (
                <div key={f.label} className="rounded-lg border border-[#262626] bg-[#0a0a0a] px-3 py-2.5">
                  <div className="text-[10px] uppercase tracking-wider text-gray-500">{f.label}</div>
                  <div className="font-mono text-xl font-bold text-white">{num(f.pts, 1)}</div>
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs leading-relaxed text-gray-500">{COPY.formatsNote}</p>
          </div>

          {/* ── Drivers ──────────────────────────────────────────────────────────────────── */}
          {drivers.length > 0 && (
            <div className="p-5 md:p-6">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">
                  {COPY.driversHeading}
                </span>
                <Popover>
                  <PopoverTrigger aria-label="How to read these drivers">
                    <Info className="h-3 w-3 text-gray-600 hover:text-gray-400" />
                  </PopoverTrigger>
                  <PopoverContent className="max-w-xs text-xs leading-relaxed">
                    {COPY.driversNote}
                  </PopoverContent>
                </Popover>
              </div>
              <ul className="mt-3 space-y-2">
                {drivers.map((d) => {
                  const positive = (d.pts ?? 0) >= 0
                  return (
                    <li key={d.feature} className="flex items-center justify-between gap-3 text-sm">
                      <span className="text-gray-300">{d.label}</span>
                      <span
                        className={`shrink-0 font-mono text-sm font-semibold ${
                          positive ? "text-[#10b981]" : "text-red-400"
                        }`}
                      >
                        {positive ? "+" : "−"}
                        {num(Math.abs(d.pts ?? 0), 1)}
                      </span>
                    </li>
                  )
                })}
              </ul>
            </div>
          )}
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-3">
          <Button asChild className="bg-[#10b981] font-semibold text-[#0a0a0a] hover:bg-[#059669]">
            <Link href={COPY.cta.href}>
              {COPY.cta.label}
              <ArrowRight className="ml-1.5 h-4 w-4" />
            </Link>
          </Button>
          <Button
            asChild
            variant="outline"
            className="border-[#262626] bg-transparent text-gray-200 hover:bg-[#1a1a1a] hover:text-white"
          >
            <Link href={COPY.secondaryCta.href}>{COPY.secondaryCta.label}</Link>
          </Button>
        </div>
      </div>
    </section>
  )
}
