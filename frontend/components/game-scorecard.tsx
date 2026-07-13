"use client"

// E9.40 — "who called it" scorecard.
//
// A completed game's final result plus a factual settle of the model's call and
// the market's benchmark. Honest-framing only: a model miss is shown as plainly
// as a hit. These are model outputs, not betting advice — no profitability
// framing of any kind on this surface.
//
// Semantics (consistent with the performance page): the model's pick is the side
// its probability favored; for the moneyline the market benchmark is the closing
// favorite; for total runs there is no directional market call to grade, so the
// closing line and the final combined total are reported as a plain fact.

import { ChevronDown } from "lucide-react"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { normalizeTeam } from "@/lib/teams"
import { cn } from "@/lib/utils"

export interface MarketScorecard {
  market_type: string
  model_side: string | null
  model_result: string | null   // "win" | "loss" | "push"
  model_prob: number | null
  market_side: string | null
  market_result: string | null
  market_prob: number | null
  total_line: number | null
  final_total: number | null
  landed: string | null          // "over" | "under" | "push"
}

export interface GameScorecardData {
  game_pk: number | null
  game_date: string | null
  home_team: string | null
  away_team: string | null
  home_team_name: string | null
  away_team_name: string | null
  home_score: number | null
  away_score: number | null
  status: string
  markets: MarketScorecard[]
}

function marketName(t: string): string {
  if (t === "h2h") return "Moneyline"
  if (t === "totals") return "Total Runs"
  return t
}

function sideLabel(marketType: string, side: string | null, sc: GameScorecardData): string {
  if (!side) return "—"
  if (marketType === "h2h") {
    if (side === "home") return normalizeTeam(sc.home_team ?? "Home")
    if (side === "away") return normalizeTeam(sc.away_team ?? "Away")
  }
  return side.charAt(0).toUpperCase() + side.slice(1)  // Over / Under
}

// A factual outcome pill: Correct / Missed / Push. Not a recommendation.
function ResultPill({ result }: { result: string | null }) {
  if (!result) return <span className="text-gray-600">—</span>
  const map: Record<string, { label: string; cls: string }> = {
    win: { label: "Correct", cls: "bg-[#10b981]/15 text-[#10b981] border-[#10b981]/30" },
    loss: { label: "Missed", cls: "bg-[#ef4444]/15 text-[#ef4444] border-[#ef4444]/30" },
    push: { label: "Push", cls: "bg-gray-700/40 text-gray-400 border-gray-600/40" },
  }
  const m = map[result] ?? { label: result, cls: "bg-gray-700/40 text-gray-400 border-gray-600/40" }
  return (
    <span className={cn("inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-semibold", m.cls)}>
      {m.label}
    </span>
  )
}

function pct(v: number | null): string {
  return v == null ? "" : `${(v * 100).toFixed(0)}%`
}

function MarketRow({ market, sc }: { market: MarketScorecard; sc: GameScorecardData }) {
  const isH2h = market.market_type === "h2h"
  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2.5">
      <div className="text-xs font-medium uppercase tracking-wide text-gray-500">
        {marketName(market.market_type)}
      </div>

      {/* Model's call */}
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm text-gray-300">
          Model called <span className="font-semibold text-white">{sideLabel(market.market_type, market.model_side, sc)}</span>
          {market.model_prob != null && (
            <span className="ml-1 font-mono text-xs text-gray-500">({pct(market.model_prob)})</span>
          )}
        </span>
        <ResultPill result={market.model_result} />
      </div>

      {/* Market benchmark — h2h: the closing favorite; totals: the de-vigged lean */}
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm text-gray-300">
          {isH2h ? "Market favored" : "Market leaned"}{" "}
          <span className="font-semibold text-white">{sideLabel(market.market_type, market.market_side, sc)}</span>
          {market.market_prob != null && (
            <span className="ml-1 font-mono text-xs text-gray-500">({pct(market.market_prob)})</span>
          )}
        </span>
        <ResultPill result={market.market_result} />
      </div>

      {/* Totals: the plain line facts */}
      {!isH2h && (
        <div className="text-xs text-gray-500">
          Closing line{" "}
          <span className="font-mono text-gray-400">{market.total_line != null ? market.total_line.toFixed(1) : "—"}</span>
          {market.final_total != null && (
            <>
              {" · "}Final total{" "}
              <span className="font-mono text-gray-400">{market.final_total}</span>
              {market.landed && (
                <span className="ml-1">
                  ({market.landed === "push" ? "Push" : market.landed.charAt(0).toUpperCase() + market.landed.slice(1)})
                </span>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

function FinalLine({ sc, className }: { sc: GameScorecardData; className?: string }) {
  const away = normalizeTeam(sc.away_team ?? "Away")
  const home = normalizeTeam(sc.home_team ?? "Home")
  return (
    <div className={cn("flex items-center gap-2 text-sm", className)}>
      <span className="inline-flex items-center rounded border border-[#262626] bg-gray-800 px-1.5 py-0.5 text-[11px] font-semibold text-gray-300">
        Final
      </span>
      <span className="font-mono text-gray-200">
        {away} {sc.away_score} — {home} {sc.home_score}
      </span>
    </div>
  )
}

/**
 * Full scorecard card — used on the pick-detail page.
 */
export function GameScorecard({ scorecard: sc, className }: { scorecard: GameScorecardData; className?: string }) {
  if (!sc || sc.status !== "Final" || !sc.markets?.length) return null
  return (
    <div className={cn("flex flex-col gap-3 rounded-xl border border-[#1e1e1e] bg-[#0a0a0a] p-4", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-white">How it played out</h3>
        <FinalLine sc={sc} />
      </div>
      <div className="flex flex-col gap-2">
        {sc.markets.map((m) => (
          <MarketRow key={m.market_type} market={m} sc={sc} />
        ))}
      </div>
      <p className="text-[11px] leading-relaxed text-gray-600">
        Factual result — the side the model favored and the side the market favored, each vs. the
        outcome. For total runs the market's lean is near-neutral (implied % shown). These are
        model outputs, not betting advice.
      </p>
    </div>
  )
}

/**
 * Compact scorecard card — used in the results grid on the tracker and dashboard
 * surfaces. Reuses the exact same settle semantics as the full card.
 */
export function GameScorecardCompact({ scorecard: sc }: { scorecard: GameScorecardData }) {
  if (!sc || sc.status !== "Final" || !sc.markets?.length) return null
  const away = normalizeTeam(sc.away_team ?? "Away")
  const home = normalizeTeam(sc.home_team ?? "Home")
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-white">{away} @ {home}</span>
        <span className="font-mono text-xs text-gray-400">
          <span className="mr-1 rounded border border-[#262626] bg-gray-800 px-1 py-0.5 text-[10px] font-semibold text-gray-300">Final</span>
          {sc.away_score}–{sc.home_score}
        </span>
      </div>
      {sc.markets.map((m) => (
        <div key={m.market_type} className="flex flex-col gap-1 border-t border-[#1a1a1a] pt-1.5">
          <div className="text-[11px] font-medium uppercase tracking-wide text-gray-600">{marketName(m.market_type)}</div>
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="text-gray-400">
              Model <span className="font-medium text-gray-200">{sideLabel(m.market_type, m.model_side, sc)}</span>
            </span>
            <ResultPill result={m.model_result} />
          </div>
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="text-gray-400">
              Market <span className="font-medium text-gray-200">{sideLabel(m.market_type, m.market_side, sc)}</span>
            </span>
            <ResultPill result={m.market_result} />
          </div>
        </div>
      ))}
    </div>
  )
}

/**
 * A "Results" section rendering a responsive grid of compact scorecards. Renders
 * nothing when there are no completed games (so callers can drop it in
 * unconditionally for the selected date).
 *
 * Collapsible: the header (title + completed count + the model/market call tally) stays visible so
 * the at-a-glance summary is always there, and the per-game grid collapses to keep the surface
 * compact. Starts collapsed by default (`defaultOpen`).
 */
export function ScorecardResults({
  scorecards,
  title = "Results",
  defaultOpen = false,
}: {
  scorecards: GameScorecardData[] | undefined
  title?: string
  defaultOpen?: boolean
}) {
  const finals = (scorecards ?? []).filter((s) => s && s.status === "Final" && s.markets?.length)
  if (!finals.length) return null

  // Tally correct calls PER MARKET (moneyline vs total runs are distinct calls; combining them into a
  // single "/2N" made the count look doubled). Decisive = correct + missed; pushes excluded.
  const tally: Record<string, { modelC: number; modelD: number; mktC: number; mktD: number }> = {}
  for (const s of finals) {
    for (const m of s.markets) {
      const t = (tally[m.market_type] ??= { modelC: 0, modelD: 0, mktC: 0, mktD: 0 })
      if (m.model_result === "win" || m.model_result === "loss") {
        t.modelD++
        if (m.model_result === "win") t.modelC++
      }
      if (m.market_result === "win" || m.market_result === "loss") {
        t.mktD++
        if (m.market_result === "win") t.mktC++
      }
    }
  }
  const tallyRows = ["h2h", "totals"]
    .filter((k) => tally[k] && (tally[k].modelD > 0 || tally[k].mktD > 0))
    .map((k) => ({ key: k, ...tally[k] }))

  return (
    <Collapsible defaultOpen={defaultOpen} className="flex flex-col gap-3">
      <CollapsibleTrigger className="group flex w-full flex-wrap items-baseline gap-x-3 gap-y-1 rounded-md text-left transition-colors hover:opacity-90">
        <ChevronDown className="h-4 w-4 shrink-0 self-center text-gray-500 transition-transform duration-200 group-data-[state=open]:rotate-180" />
        <h2 className="text-base font-semibold text-white">{title}</h2>
        <span className="text-xs text-gray-500">{finals.length} completed {finals.length === 1 ? "game" : "games"}</span>
        {tallyRows.map((t) => (
          <span key={t.key} className="text-xs text-gray-500">
            <span className="text-gray-400">{marketName(t.key)}</span>{" "}
            <span className="text-gray-500">Model</span>{" "}
            <span className="font-mono text-gray-300">{t.modelC}/{t.modelD}</span>
            <span className="mx-1 text-gray-600">·</span>
            <span className="text-gray-500">Market</span>{" "}
            <span className="font-mono text-gray-300">{t.mktC}/{t.mktD}</span>
          </span>
        ))}
        <span className="ml-auto self-center text-[11px] text-gray-600 group-data-[state=open]:hidden">Show</span>
        <span className="ml-auto hidden self-center text-[11px] text-gray-600 group-data-[state=open]:inline">Hide</span>
      </CollapsibleTrigger>
      <CollapsibleContent className="flex flex-col gap-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {finals.map((s) => (
            <GameScorecardCompact key={s.game_pk ?? Math.random()} scorecard={s} />
          ))}
        </div>
        <p className="text-[11px] leading-relaxed text-gray-600">
          The side the model favored and the side the market favored, each vs. the final outcome — one
          call per market, pushes excluded from the tally. A miss is shown as plainly as a hit. Model
          outputs, not betting advice.
        </p>
      </CollapsibleContent>
    </Collapsible>
  )
}
