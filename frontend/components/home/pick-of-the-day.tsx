"use client"

import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { CheckCircle2, Clock, Info, Lock, XCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { ProbabilityBar } from "@/components/probability-bar"
import { cdnFetch } from "@/lib/api"
import { MLB_PRODUCT_TAGLINE, MLB_PROOF as COPY } from "@/lib/home-copy"

/**
 * E9.46 — the live model-vs-market element on the home page.
 *
 * ══ WHAT THIS BLOCK IS, AND THE ONE THING IT IS NOT ═══════════════════════════════════════════
 *
 * It is a DEMONSTRATION of the product: one game's model-vs-market read, with the uncertainty
 * around our estimate and yesterday's graded result beside it. It is not a recommendation, and the
 * difference is not a matter of tone — `best_alpha = 0`, the betting program has six recorded
 * no-edge results, so a home page that told a stranger to place this bet would be making the one
 * claim this company has repeatedly measured and failed to find.
 *
 * ⚠️⚠️ WHICH GAME, EXACTLY — AND THE FIRST CUT OF THIS FILE GOT IT WRONG IN PRODUCTION COPY.
 * It said "today's widest disagreement between our model and the market". It is not. The serving
 * query (`_FEATURED_TODAY_SERVING_SQL`) filters to `layer4_h2h_conviction_flag = TRUE` and then
 * orders `game_datetime ASC … LIMIT 1` — so it is the EARLIEST-STARTING qualifying game of the day,
 * and NOTHING in the selection considers the size of the gap. The flag itself is
 * `|calibrated_win_prob − P(run_diff > 0)| ≤ 0.02` (`predict_today.py`): two independent Credence
 * estimators agreeing with each other, computed without reference to the odds at all.
 *
 * ⇒ the copy in `MLB_PROOF.frame` describes exactly that, and the badge says "our models agree"
 * rather than anything about the market. Do not reintroduce superlatives here — "widest", "biggest"
 * and "strongest" are all claims this selection cannot support.
 *
 * `COPY.frame` carries that in words and renders ABOVE the numbers, because a visitor reads the
 * big figure first.
 *
 * ══ THREE DESIGN DECISIONS THAT ARE NOT PREFERENCES ═══════════════════════════════════════════
 *
 * 1. ⭐ NUMBERS AND STATIC LABELS ONLY — no `ai_summary`, no `model_narrative`. Both are served
 *    prose written for the signed-in analysis surfaces, and both use "edge" freely (the live
 *    payload on 2026-08-07: "a +3.2pp edge over the Bovada closing line"). Rendering them here
 *    would put copy this repo does not control, does not version, and cannot screen onto the one
 *    page where the claim discipline is strictest — and the denylist scan in
 *    `home-positioning.spec.ts` would then be asserting against a sentence the API can change
 *    under it. The served field `edge` is displayed as "Gap" for the same reason: it is a
 *    difference between two probabilities, and naming it that is both honest and free.
 *
 * 2. ⭐ AN EMPTY OR FAILED READ MUST NEVER PRODUCE A BLANK BLOCK, and the two are DIFFERENT
 *    STATES. `game_pk: null` means the model published nothing today — a real answer, and one
 *    this product is proud of. A thrown fetch means the PAGE could not reach the model, which is
 *    our failure and says nothing about the slate. Collapsing them into one message would state a
 *    falsehood in one of the two cases. Neither ever renders nothing: a section that vanishes on
 *    an empty read is indistinguishable from a broken page (the E9.26b silent-`[]` class), and the
 *    hero above is static precisely so no read can ever leave the top of the page bare.
 *
 * 3. ⭐ CLIENT-SIDE, VIA `cdnFetch`. The previous home page fetched this server-side, which had
 *    two costs: it made the whole marketing page dynamic on every request for one live figure, and
 *    it put the block permanently beyond Playwright's reach (`page.route` intercepts the BROWSER;
 *    it cannot see a server component's fetch). Moving it client-side lets the positioning page go
 *    static AND lets `home-positioning.spec.ts` exercise the populated, empty and failed paths
 *    against real captured bytes. The endpoint is public — the previous server-side call sent no
 *    token either — so no auth changes with it.
 */

// The subset of `FeaturedPickResponse` this surface reads. Deliberately narrow: a field absent
// from this type is a field the marketing page cannot accidentally start rendering.
export type FeaturedPick = {
  game_pk: number | null
  matchup: string | null
  game_time_et: string | null
  market_type: string | null
  edge: number | null
  model_prob: number | null
  market_prob: number | null
  ci_low: number | null
  ci_high: number | null
  conviction_label: string | null
  is_stale?: boolean
  is_preliminary?: boolean
  pick_date?: string | null
  home_team?: string | null
  away_team?: string | null
  pick_side?: string | null
  yesterday?: {
    matchup: string
    market_type: string
    outcome: string
    status?: "win" | "loss" | "pending"
  } | null
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <section id="today" className="scroll-mt-20 border-t border-[#262626] py-16 md:py-24">
      <div className="mx-auto max-w-3xl px-4">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#10b981]">
            {COPY.eyebrow}
          </p>
          {/* ⚠️ The MLB product's own tagline, kept from the pre-E9.46 hero where it was the
              COMPANY headline (operator, 2026-08-08). It lives here and only here: scoped to the
              betting product, and adjacent to `COPY.recordNote` below, which states plainly that no
              durable advantage over the closing market has been shown. That adjacency is what keeps
              the word "edge" honest — it names the model-vs-market difference this card quantifies,
              not a demonstrated advantage. `test_e9_46_home_copy.py` pins the scoping. */}
          <span className="text-xs italic text-gray-600">{MLB_PRODUCT_TAGLINE}</span>
        </div>
        {/* ⛔ The frame renders BEFORE the card in every state, including the empty and failed
            ones. It is what makes this a transparency feature rather than a tout, and a state
            that dropped it would be the tout. */}
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-gray-400">{COPY.frame}</p>
        <div className="mt-8">{children}</div>
      </div>
    </section>
  )
}

function Card({ children, muted = false }: { children: React.ReactNode; muted?: boolean }) {
  return (
    <div
      className="rounded-xl border border-[#262626] bg-[#141414] p-6 shadow-xl shadow-black/40 md:p-8"
      style={{ borderLeft: `3px solid ${muted ? "#3f3f46" : "#10b981"}` }}
    >
      {children}
    </div>
  )
}

function Stat({ label, value, tone, stat }: { label: string; value: string; tone: string; stat: string }) {
  return (
    <div data-stat={stat} className="rounded-lg border border-[#262626] bg-[#0a0a0a] px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-gray-500">{label}</div>
      <div className={`font-mono text-sm font-semibold ${tone}`}>{value}</div>
    </div>
  )
}

export function PickOfTheDay() {
  const { data, isLoading, isError } = useQuery<FeaturedPick>({
    queryKey: ["home", "featured-pick"],
    // G100-D1 — through our own CDN, not the API Lambda. This call carries NO token (it never
    // has), so every visitor gets the identical payload and it is cacheable once for everybody.
    // The landing page is the most-hit anonymous surface we have, so before this it was one API
    // Gateway request + one Lambda invocation per visit; now it is one per `s-maxage` window.
    queryFn: () => cdnFetch("/api/public/featured"),
    // The serving write lands once in the morning and again after lineups confirm; a visitor who
    // leaves the tab open does not need it re-fetched every minute.
    staleTime: 5 * 60 * 1000,
    retry: 1,
  })

  if (isLoading) {
    return (
      <Shell>
        <Card muted>
          <div className="h-4 w-40 animate-pulse rounded bg-[#262626]" />
          <div className="mt-4 h-9 w-64 animate-pulse rounded bg-[#262626]" />
          <div className="mt-5 h-16 w-full animate-pulse rounded bg-[#1c1c1c]" />
        </Card>
      </Shell>
    )
  }

  // ⚠️ TWO DISTINCT FAILURES, TWO DISTINCT MESSAGES — see the header note. `isError` is the page
  // failing to reach the model; a null `game_pk` is the model having published nothing.
  if (isError || !data) {
    return (
      <Shell>
        <Card muted>
          <p className="text-sm leading-relaxed text-gray-400">{COPY.unavailable}</p>
          <Link
            href={COPY.fullCard.href}
            className="mt-4 inline-block text-sm text-[#10b981] underline-offset-4 hover:underline"
          >
            {COPY.fullCard.label} &rarr;
          </Link>
        </Card>
      </Shell>
    )
  }

  if (data.game_pk == null) {
    return (
      <Shell>
        <Card muted>
          <p className="text-sm leading-relaxed text-gray-400">{COPY.empty}</p>
        </Card>
      </Shell>
    )
  }

  // `model_prob` is always P(home) for h2h and P(over) for totals. Below 0.5 the model's lean is
  // on the away side / the under, so flip every probability onto the side being described —
  // otherwise the bar and the numbers describe the opposite outcome to the label above them.
  const flip = data.model_prob != null && data.model_prob < 0.5
  const modelProb = flip && data.model_prob != null ? 1 - data.model_prob : data.model_prob
  const marketProb = flip && data.market_prob != null ? 1 - data.market_prob : data.market_prob
  const ciLow = flip && data.ci_high != null ? 1 - data.ci_high : data.ci_low
  const ciHigh = flip && data.ci_low != null ? 1 - data.ci_low : data.ci_high

  const leanLabel =
    data.market_type === "h2h"
      ? (data.pick_side === "away" ? data.away_team : data.home_team) ?? null
      : data.pick_side
        ? data.pick_side.charAt(0).toUpperCase() + data.pick_side.slice(1)
        : null

  const pct = (v: number | null | undefined) => (v == null ? null : `${(v * 100).toFixed(1)}%`)

  return (
    <Shell>
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-medium uppercase tracking-widest text-gray-500">
            {data.market_type === "h2h" ? "Moneyline" : "Total runs"}
          </span>
          {data.pick_date && (
            <span className="text-xs text-gray-500">
              {new Date(data.pick_date + "T12:00:00").toLocaleDateString("en-US", {
                month: "long",
                day: "numeric",
              })}
            </span>
          )}
        </div>

        {data.is_stale && (
          <p className="mt-3 rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-xs text-gray-400">
            {COPY.staleNote}
          </p>
        )}

        <h3 className="mt-4 text-3xl font-bold tracking-tight text-white md:text-4xl">
          {data.matchup}
        </h3>
        {leanLabel && (
          // ⚠️ "leans" and not "picks". The model produces a probability, and a probability of 52%
          // is a lean; presenting it as a selection overstates what the number says.
          <p className="mt-1.5 text-base font-semibold text-[#10b981]">
            Our model leans {leanLabel}
          </p>
        )}
        {data.game_time_et && <p className="mt-1 text-sm text-gray-500">{data.game_time_et}</p>}

        <div className="mt-5 flex flex-wrap gap-2">
          {/* ⚠️⚠️ THE SERVED `conviction_label` IS DELIBERATELY NOT RENDERED, and this is the
              single most important correction in this component.

              It is a HARDCODED CONSTANT — the literal string "HIGH CONVICTION", stamped on every
              featured pick in both `write_serving_store.py` and the API's own fallback. It
              classifies nothing. Worse, a bettor reads "high conviction" as "we are confident this
              team wins", which is the exact claim `best_alpha = 0` forbids.

              What the row actually satisfies is `layer4_h2h_conviction_flag`, defined in
              `predict_today.py` as `|calibrated_win_prob − P(run_diff > 0)| ≤ 0.02` — two
              INDEPENDENT Credence estimators agreeing with each other, computed without reference
              to the odds. So the badge states that, and the popover keeps it from being read as a
              promise about the result. (Both alternatives considered were false: "high model
              disagreement" inverts the flag's meaning, and "large model–market gap" describes
              neither the flag nor the selection, which orders by earliest start time.) */}
          {!data.is_stale && data.conviction_label && (
            <Popover>
              <PopoverTrigger aria-label="What our models agreeing means">
                <Badge className="cursor-help border border-[#10b981]/30 bg-[#10b981]/15 text-xs font-bold uppercase tracking-widest text-[#10b981]">
                  {COPY.agreementBadge}
                  <Info className="ml-1 h-3 w-3" />
                </Badge>
              </PopoverTrigger>
              <PopoverContent className="max-w-xs text-xs leading-relaxed">
                {COPY.agreementHint}
              </PopoverContent>
            </Popover>
          )}
          {data.is_preliminary && (
            <Badge className="border border-amber-500/25 bg-amber-500/15 text-xs font-semibold text-amber-400">
              {COPY.preliminaryNote}
            </Badge>
          )}
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {modelProb != null && (
            <Stat stat="model" label={COPY.labels.model} value={pct(modelProb)!} tone="text-white" />
          )}
          {marketProb != null && (
            <Stat stat="market" label={COPY.labels.market} value={pct(marketProb)!} tone="text-gray-400" />
          )}
          {data.edge != null && (
            <div data-stat="gap" className="rounded-lg border border-[#262626] bg-[#0a0a0a] px-3 py-2">
              <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-gray-500">
                {COPY.labels.gap}
                {/* A Popover, not a hover tooltip: the E9.63/NF3 lesson is that a hover-only
                    explanation is unreachable on a phone, and this one is what stops "Gap" being
                    read as a claim to an advantage. */}
                <Popover>
                  <PopoverTrigger aria-label="What the gap means">
                    <Info className="h-3 w-3 text-gray-600 hover:text-gray-400" />
                  </PopoverTrigger>
                  <PopoverContent className="max-w-xs text-xs leading-relaxed">
                    {COPY.gapHint}
                  </PopoverContent>
                </Popover>
              </div>
              <div className="font-mono text-sm font-semibold text-[#10b981]">
                +{Math.abs(data.edge).toFixed(1)} pts
              </div>
            </div>
          )}
          {ciLow != null && ciHigh != null && (
            <Stat
              stat="range"
              label={COPY.labels.range}
              value={`${pct(ciLow)}–${pct(ciHigh)}`}
              tone="text-gray-400"
            />
          )}
        </div>

        {modelProb != null && marketProb != null && (
          <div className="mt-6">
            <ProbabilityBar
              ciLow={ciLow}
              ciHigh={ciHigh}
              modelProb={modelProb}
              marketProb={marketProb}
              showHighConviction={false}
              teamLabel={data.market_type === "h2h" ? leanLabel : null}
            />
          </div>
        )}

        {/* ⭐ THE PUBLIC HALF OF THE HONEST RECORD. `/performance` needs an account, so for a
            logged-out stranger this row is the only self-grading they can see without signing up —
            and it renders a loss exactly as prominently as a win. That is the whole point of it. */}
        {data.yesterday && (
          <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-[#262626] pt-5">
            <span className="text-xs text-gray-500">
              <span className="font-medium text-gray-400">{COPY.yesterdayLabel}:</span>{" "}
              {data.yesterday.matchup}
            </span>
            {data.yesterday.status === "win" ? (
              <Badge className="border border-[#10b981]/25 bg-[#10b981]/10 text-xs text-[#10b981]">
                <CheckCircle2 className="mr-1 h-3 w-3" />
                {data.yesterday.outcome}
              </Badge>
            ) : data.yesterday.status === "loss" ? (
              <Badge className="border border-red-500/25 bg-red-500/10 text-xs text-red-400">
                <XCircle className="mr-1 h-3 w-3" />
                {data.yesterday.outcome}
              </Badge>
            ) : (
              <Badge className="border border-gray-500/25 bg-gray-500/10 text-xs text-gray-400">
                <Clock className="mr-1 h-3 w-3" />
                {data.yesterday.outcome}
              </Badge>
            )}
          </div>
        )}
      </Card>

      {/* ⭐ THE RECORD SENTENCE. Two jobs at once: it must not claim an edge, and it must not
          pretend we fail to measure one. The daily model-vs-market record is real and is a genuine
          part of the product; what it has not shown is a durable advantage over the closing
          market. Dropping either half would be a different kind of dishonest. */}
      <p className="mt-5 text-sm leading-relaxed text-gray-500">{COPY.recordNote}</p>

      <p className="mt-4 text-center text-sm">
        <Link
          href={COPY.fullCard.href}
          className="inline-flex items-center gap-1.5 text-gray-500 underline-offset-4 transition-colors hover:text-[#10b981] hover:underline"
        >
          {COPY.fullCard.label}
          {COPY.fullCard.needsAccount && <Lock className="h-3 w-3" />}
          <span aria-hidden="true">&rarr;</span>
        </Link>
      </p>
    </Shell>
  )
}
