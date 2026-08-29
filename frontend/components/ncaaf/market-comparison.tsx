"use client"

// NCAAF-P3.2 — the transparency panel: our number and the market's, side by side.
//
// ⚠️⚠️ THIS IS THE HIGHEST-RISK COMPONENT ON THE SURFACE and the spec's overlap check says so in
// as many words. Three rules bind it, and each of them is a recorded verdict rather than a taste:
//
//  1. ⛔ NO DIFFERENCE COLUMN, EVER. The served contract deliberately declares none — "Model −7,
//     market −3.5 is a fact a reader can see; 'model beats market by 3.5' is the claim VAL1's null
//     forbids, and a signed difference column is one rename away from being read as exactly that"
//     (`NcaafMarketLine`'s own docstring). So this component renders two numbers and stops. It does
//     not subtract them, sort by the gap, colour by the gap, or flag one as larger.
//
//  2. ⛔ NO SIDE IS MARKED. Nothing here says which number is better, and there is no highlight,
//     badge, arrow or ordering that would let a reader infer that we think one is. `best_alpha = 0`
//     — VAL1 measured ATS 0.496 against the close, indistinguishable from a placebo.
//
//  3. ⭐ AN ABSENT LINE IS A STATED ABSENCE, NEVER A BLANK AND NEVER A ZERO. In a two-column
//     comparison a blank cell reads as parity and a zero reads as a line of zero; both would be a
//     fabricated market view. So the absence is DESIGNED FOR rather than tolerated.
//     ⚠️ It was the ONLY branch a reader could meet through P3.2 (the 2026 capture could not reach
//     a kickoff until it was PAST — P3.1 closeout item 2). NCAAF-ODDS-LIVE's ahead-of-kickoff feed
//     makes `available` the ordinary case once its data lands — but the absence does NOT become
//     rare, because a leakage refusal still serves it. Both are live paths; neither may be coded
//     as the exceptional one.
//
// ══ THE ONE CONVERSION, AND WHY IT IS NOT A DERIVATION ════════════════════════════════════════
//
// The book quotes a home SPREAD (negative = home favoured); the model publishes a home MARGIN
// (positive = home favoured). Those are the same quantity under opposite sign conventions, so the
// market column negates the spread to put both numbers in the model's unit and under one row
// heading. That is a units conversion on a served number, not a model quantity: no probability, no
// σ, no interval and no comparison is computed anywhere in this file.

import {
  MARKET_ABSENT_LABEL,
  MARKET_COLUMN_LABEL,
  MARKET_IMPLIED_HINT,
  FRAMING_CHANGED,
  MARKET_PANEL_FRAMING,
  MARKET_PANEL_LABEL,
  MARKET_REASON_COPY,
  MARKET_REASON_FALLBACK,
  MODEL_COLUMN_LABEL,
  ROW_HOME_MARGIN,
  ROW_HOME_WIN,
  ROW_TOTAL,
} from "@/lib/ncaaf-copy"
import { isMarketBlindProjection, type NcaafGamePrediction } from "@/lib/ncaaf"
import { formatProbability } from "./win-probability"

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v)

/**
 * The single number we quote for a distribution, and THE NAME OF THE NUMBER WE QUOTED.
 *
 * ⭐ The median and the mean are different numbers on a skewed predictive, and P2.5 measured a real
 * right-skew on the college total. Substituting one for the other under the other's label is the
 * mislabelling class this repo keeps paying for (INC-41's two unequal numbers under one word), so
 * the label travels with the value: the served median when the quantile ladder carries one,
 * otherwise the served mean, said out loud.
 */
export function modelCentre(
  dist: { mu: number | null; quantile_levels: number[]; quantiles: number[] },
): { value: number | null; label: string } {
  for (let i = 0; i < dist.quantile_levels.length; i++) {
    if (dist.quantile_levels[i] === 0.5 && isNum(dist.quantiles[i])) {
      return { value: dist.quantiles[i], label: "median" }
    }
  }
  return isNum(dist.mu) ? { value: dist.mu, label: "mean" } : { value: null, label: "median" }
}

const fmtSigned = (n: number | null) =>
  n == null ? "—" : `${n > 0 ? "+" : ""}${(Object.is(n, -0) ? 0 : n).toFixed(1)}`
const fmt1 = (n: number | null) => (n == null ? "—" : (Object.is(n, -0) ? 0 : n).toFixed(1))

function Row({
  label,
  model,
  market,
  note,
  testId,
}: {
  label: string
  model: string
  market: string | null
  note?: string
  testId: string
}) {
  return (
    <div data-testid={testId} className="grid grid-cols-[1fr_auto_auto] items-baseline gap-x-3 py-1.5">
      <span className="text-xs text-gray-400">{label}</span>
      <span
        data-testid={`${testId}-model`}
        className="w-16 text-right text-sm tabular-nums text-white"
      >
        {model}
      </span>
      <span
        data-testid={`${testId}-market`}
        className="w-24 text-right text-sm tabular-nums text-gray-400"
      >
        {market ?? <span className="text-[11px] text-gray-500">{MARKET_ABSENT_LABEL}</span>}
      </span>
      {note && <p className="col-span-3 pt-0.5 text-[11px] leading-snug text-gray-500">{note}</p>}
    </div>
  )
}

export function MarketComparison({
  game,
  testId = "ncaaf-market-comparison",
}: {
  game: NcaafGamePrediction
  testId?: string
}) {
  const market = game.market
  const available = market.status === "available"
  const margin = modelCentre(game.margin)
  const total = modelCentre(game.total)
  const postureHolds = isMarketBlindProjection(game.framing)

  // See the header: a units conversion on a served number, not a derivation.
  const marketHomeMargin = available && isNum(market.home_spread) ? -market.home_spread : null

  return (
    <div
      data-testid={testId}
      data-market-status={market.status}
      data-posture={postureHolds ? "market_blind_projection" : "changed"}
      className="space-y-2"
    >
      <div className="text-[10px] uppercase tracking-widest text-gray-500">{MARKET_PANEL_LABEL}</div>

      <div className="grid grid-cols-[1fr_auto_auto] gap-x-3 border-b border-[#1e1e1e] pb-1">
        <span />
        <span className="w-16 text-right text-[10px] uppercase tracking-widest text-gray-500">
          {MODEL_COLUMN_LABEL}
        </span>
        <span className="w-24 text-right text-[10px] uppercase tracking-widest text-gray-500">
          {MARKET_COLUMN_LABEL}
        </span>
      </div>

      <div className="divide-y divide-[#161616]">
        <Row
          testId={`${testId}-margin`}
          label={`${ROW_HOME_MARGIN} (${margin.label})`}
          model={fmtSigned(margin.value)}
          market={marketHomeMargin == null ? null : fmtSigned(marketHomeMargin)}
        />
        <Row
          testId={`${testId}-total`}
          label={`${ROW_TOTAL} (${total.label})`}
          model={fmt1(total.value)}
          market={available && isNum(market.total) ? fmt1(market.total) : null}
        />
        <Row
          testId={`${testId}-winprob`}
          label={ROW_HOME_WIN}
          model={formatProbability(game.win_probability.home)}
          market={
            available && isNum(market.home_moneyline_implied_probability)
              ? formatProbability(market.home_moneyline_implied_probability)
              : null
          }
          note={
            available && isNum(market.home_moneyline_implied_probability)
              ? MARKET_IMPLIED_HINT
              : undefined
          }
        />
      </div>

      {!available && (
        <p data-testid={`${testId}-absent-reason`} className="text-[11px] leading-snug text-gray-500">
          {(market.reason && MARKET_REASON_COPY[market.reason]) || MARKET_REASON_FALLBACK}
        </p>
      )}

      {/* See `isMarketBlindProjection`: our framing sentence is warranted by the payload's flags
          and by nothing else, so on a payload that stops carrying them we withdraw it and show the
          publisher's own disclosure instead — a refusal, never a re-interpretation. */}
      {postureHolds ? (
        <p data-testid={`${testId}-framing`} className="text-[11px] leading-snug text-gray-500">
          {MARKET_PANEL_FRAMING}
        </p>
      ) : (
        <div data-testid={`${testId}-framing-withdrawn`} className="space-y-1">
          <p className="text-[11px] leading-snug text-amber-300/80">{FRAMING_CHANGED}</p>
          <p className="text-[11px] leading-snug text-gray-500">{game.framing.disclosure}</p>
        </div>
      )}
    </div>
  )
}
