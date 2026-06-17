"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import posthog from "posthog-js"
import { useQuery } from "@tanstack/react-query"
import { AuthGuard } from "@/components/auth-guard"
import { ReportDataIssue } from "@/components/report-data-issue"
import { useAuth } from "@/lib/auth-context"
import { Nav } from "@/components/nav"
import { apiFetch } from "@/lib/api"
import Link from "next/link"
import { ChevronLeft, ChevronDown, Info } from "lucide-react"
import { normalizeTeam, espnLogoPath } from "@/lib/teams"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import dynamic from "next/dynamic"
import type { PickExplanationPayload } from "@/components/pick-explanation"

// ---------------------------------------------------------------------------
// A0.4.32 — Book odds comparison types
// ---------------------------------------------------------------------------

type BookOddsH2H = {
  book_key: string
  book_name: string
  is_sharp_reference: boolean
  home_american: number | null
  away_american: number | null
  home_decimal: number | null
  away_decimal: number | null
  market_bet_pct_home: number | null
  model_prob_home: number | null
  ev_home: number | null
  edge_home: number | null
  kelly_home: number | null
  odds_as_of: string | null
}

type BookOddsTotals = {
  book_key: string
  book_name: string
  is_sharp_reference: boolean
  line: number | null
  over_american: number | null
  under_american: number | null
  over_decimal: number | null
  under_decimal: number | null
  market_bet_pct_over: number | null
  model_prob_over: number | null
  model_prob_under: number | null
  p_push: number | null
  ev_over: number | null
  ev_under: number | null
  edge_over: number | null
  kelly_over: number | null
  odds_as_of: string | null
}

type BookOddsComparison = {
  game_pk: number
  home_team: string | null
  away_team: string | null
  pred_total_runs: number | null
  totals_r: number | null
  h2h: BookOddsH2H[]
  totals: BookOddsTotals[]
}

const PickExplanationSection = dynamic(
  () => import("@/components/pick-explanation").then((m) => ({ default: m.PickExplanationSection })),
  { ssr: false, loading: () => null },
)
const ServedTierBadge = dynamic(
  () => import("@/components/pick-explanation").then((m) => ({ default: m.ServedTierBadge })),
  { ssr: false, loading: () => null },
)

// ---------------------------------------------------------------------------
// Types matching GameDetailResponse
// ---------------------------------------------------------------------------

type Pick = {
  market_type: string
  model_prob: number | null
  bovada_devig_prob: number | null
  edge: number | null
  game_conviction_score: number | null
  gate_signals_met: number | null
  win_prob_ci_low: number | null
  win_prob_ci_high: number | null
  win_prob_ci_width: number | null
  home_team: string | null
  away_team: string | null
  pick_side: string | null
  game_start_utc: string | null
  model_total_runs: number | null
  market_total_line: number | null
  game_date: string | null
  predicted_at: string | null
}

type StarterStats = {
  pitcher_id: number | null
  name: string | null
  is_opener: boolean
  // Current season to date (before game date)
  season: number | null
  starts: number | null
  ra9: number | null
  whip: number | null
  k_pct: number | null
  // Prior full season — shown when current-season starts < 8
  prior_season: number | null
  prior_starts: number | null
  prior_ra9: number | null
  prior_whip: number | null
  prior_k_pct: number | null
}

type TeamPerfStats = {
  off_woba_30d: number | null
  off_xwoba_30d: number | null
  off_runs_per_game_30d: number | null
  starter_xwoba_against_30d: number | null
  starter_k_pct_30d: number | null
  starter_hand: string | null
  lineup_vs_sp_xwoba_adj: number | null
  bp_xwoba_against_14d: number | null
  bp_innings_pitched_14d: number | null
  days_rest: number | null
}

type LineupPlayer = {
  slot: number
  player_id: number | null
  player_name: string | null
  position: string | null
  season_ops: number | null
  season_xwoba: number | null
  game_pa: number | null
  game_ab: number | null
  game_h: number | null
  game_k: number | null
  game_bb: number | null
  game_hr: number | null
  game_xwoba: number | null
}

type GameDetailData = {
  picks: Pick[]
  total: number
  home_team_name: string | null
  away_team_name: string | null
  game_score: {
    home_score: number | null
    away_score: number | null
    status: string
    home_wins: number | null
    home_losses: number | null
    away_wins: number | null
    away_losses: number | null
    home_pyth_pct: number | null
    home_pyth_residual: number | null
    away_pyth_pct: number | null
    away_pyth_residual: number | null
  } | null
  starters: { home: StarterStats | null; away: StarterStats | null } | null
  bovada_lines: {
    h2h: { home_american: number | null; away_american: number | null; snapshot_utc: string | null } | null
    totals: { line: number | null; over_american: number | null; under_american: number | null; snapshot_utc: string | null } | null
  } | null
  team_features: {
    home: TeamPerfStats | null
    away: TeamPerfStats | null
    park_run_factor: number | null
    elo_diff: number | null
  } | null
  lineups: { home: LineupPlayer[]; away: LineupPlayer[] } | null
  weather: {
    temp_f: number | null
    wind_speed_mph: number | null
    wind_component_mph: number | null
    is_dome: boolean
    observation_type: string | null
  } | null
  public_betting: {
    home_ml_money_pct: number | null
    away_ml_money_pct: number | null
    home_ml_ticket_pct: number | null
    away_ml_ticket_pct: number | null
    over_money_pct: number | null
    under_money_pct: number | null
    over_ticket_pct: number | null
    under_ticket_pct: number | null
    ml_sharp_signal: number | null
    total_sharp_signal: number | null
  } | null
  line_movement: {
    open_home_win_prob: number | null
    pregame_home_win_prob: number | null
    h2h_line_movement: number | null
    open_total_line: number | null
    pregame_total_line: number | null
    total_line_movement: number | null
  } | null
  umpire: {
    name: string | null
    k_pct_zscore: number | null
    runs_per_game_zscore: number | null
    run_impact_zscore: number | null
    bb_pct_zscore: number | null
    games_sample: number | null
  } | null
  game_context: {
    home_form: { l5_wins: number | null; l5_losses: number | null; l5_games: number | null; l10_wins: number | null; l10_losses: number | null; l10_games: number | null } | null
    away_form: { l5_wins: number | null; l5_losses: number | null; l5_games: number | null; l10_wins: number | null; l10_losses: number | null; l10_games: number | null } | null
    h2h: { home_wins: number | null; away_wins: number | null; games_played: number | null; avg_total_runs: number | null } | null
  } | null
  // Story 30.15 — model explanation
  pick_explanation: PickExplanationPayload | null
  pick_narrative: string | null
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function marketLabel(pick: Pick): string {
  const edge = pick.edge ?? 0
  if (pick.market_type === "totals") {
    const line = pick.market_total_line != null ? ` ${Number(pick.market_total_line).toFixed(1)}` : ""
    return `${edge >= 0 ? "Over" : "Under"}${line}`
  }
  return edge >= 0 ? `${pick.home_team ?? "Home"} ML` : `${pick.away_team ?? "Away"} ML`
}

function convictionLabel(score: number): string {
  if (score >= 0.65) return "HIGH"
  if (score >= 0.45) return "MED"
  return "LOW"
}

function convictionBadgeClass(score: number): string {
  if (score >= 0.65) return "bg-[#10b981] text-[#0a0a0a]"
  if (score >= 0.45) return "bg-[#f59e0b] text-[#0a0a0a]"
  return "bg-gray-600 text-white"
}

function formatEdge(edge: number): string {
  return `+${(Math.abs(edge) * 100).toFixed(1)}%`
}

function fmtAmerican(n: number | null | undefined): string {
  if (n == null) return "—"
  return n > 0 ? `+${n}` : String(n)
}

function fmtStat(n: number | null | undefined, digits = 3): string {
  if (n == null) return "—"
  return n.toFixed(digits)
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return "—"
  return `${(n * 100).toFixed(1)}%`
}

function fmtGameTime(utc: string | null): string | null {
  if (!utc) return null
  const iso = utc.endsWith("Z") || /[+-]\d\d:?\d\d$/.test(utc) ? utc : utc + "Z"
  const d = new Date(iso)
  if (isNaN(d.getTime())) return null
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", timeZoneName: "short" })
}

// ---------------------------------------------------------------------------
// A0.4.32 — BookOddsSection helpers + component
// ---------------------------------------------------------------------------

const BOOK_ORDER = ["pinnacle", "betmgm", "caesars", "fanduel", "draftkings", "bovada"]
const BOOK_LABELS: Record<string, string> = {
  pinnacle: "Pinnacle",
  betmgm: "BetMGM",
  caesars: "Caesars",
  fanduel: "FanDuel",
  draftkings: "DraftKings",
  bovada: "Bovada",
}

function fmtEV(ev: number | null | undefined): string {
  if (ev == null) return "—"
  const pct = (ev * 100).toFixed(1)
  return ev >= 0 ? `+${pct}%` : `${pct}%`
}

function evColor(ev: number | null | undefined): string {
  if (ev == null) return "text-gray-500"
  if (ev > 0.01) return "text-[#10b981]"
  if (ev < -0.01) return "text-[#f87171]"
  return "text-gray-400"
}

function edgeColor(edge: number | null | undefined): string {
  if (edge == null) return "text-gray-500"
  if (edge > 0.01) return "text-[#10b981]"
  if (edge < -0.01) return "text-[#f87171]"
  return "text-gray-400"
}

function fmtOddsTime(isoTs: string | null | undefined): string | null {
  if (!isoTs) return null
  try {
    const d = new Date(isoTs.endsWith("Z") ? isoTs : isoTs + "Z")
    return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", timeZoneName: "short" })
  } catch {
    return null
  }
}

function BookOddsSection({
  bookOdds,
  homeFullName,
  awayFullName,
  selectedBook,
  setSelectedBook,
}: {
  bookOdds: BookOddsComparison
  homeFullName: string
  awayFullName: string
  selectedBook: string
  setSelectedBook: (b: string) => void
}) {
  const hasH2H = bookOdds.h2h.some((b) => b.home_american != null)
  const hasTotals = bookOdds.totals.some((b) => b.line != null)
  if (!hasH2H && !hasTotals) return null

  const selH2H = bookOdds.h2h.find((b) => b.book_key === selectedBook)
  const selTotals = bookOdds.totals.find((b) => b.book_key === selectedBook)
  const pinnacleH2H = bookOdds.h2h.find((b) => b.book_key === "pinnacle")
  const pinnacleTotals = bookOdds.totals.find((b) => b.book_key === "pinnacle")
  // Most recent snapshot time across h2h and totals for the selected book
  const oddsTimestamp = selH2H?.odds_as_of ?? selTotals?.odds_as_of ?? null
  const oddsTimeLabel = fmtOddsTime(oddsTimestamp)

  const availableBooks = BOOK_ORDER.filter((k) => {
    const h = bookOdds.h2h.find((b) => b.book_key === k)
    const t = bookOdds.totals.find((b) => b.book_key === k)
    return (h?.home_american != null) || (t?.line != null)
  })

  return (
    <Collapsible
      defaultOpen={false}
      className="rounded-xl border border-[#262626] bg-[#141414] overflow-hidden"
    >
      <CollapsibleTrigger asChild>
        <button className="w-full flex items-center justify-between px-6 py-4 hover:bg-[#1a1a1a] transition-colors text-left">
          <span className="flex items-center gap-2.5">
            <span className="w-1 h-5 rounded-full bg-[#10b981] shrink-0" />
            <span className="text-base font-bold text-white">Book Comparison</span>
            <Tooltip>
              <TooltipTrigger asChild>
                <Info className="h-3.5 w-3.5 text-gray-600 cursor-help" />
              </TooltipTrigger>
              <TooltipContent side="top" className="max-w-[280px] text-xs leading-relaxed">
                Market transparency tool. Our h2h and totals models have no demonstrated market edge — most EVs here will be ≈0 or negative after vig. Pinnacle is the sharpest, lowest-vig reference. All bets are manual and at your own discretion.
              </TooltipContent>
            </Tooltip>
          </span>
          <ChevronDown className="h-4 w-4 text-gray-500 transition-transform duration-200 group-data-[state=open]:rotate-180 shrink-0" />
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="px-6 pb-5 space-y-4">
          {/* Disclaimer + vig explainer */}
          <div className="rounded-lg bg-[#111] border border-[#1e1e1e] px-4 py-3 space-y-2">
            <p className="text-xs text-gray-400 leading-relaxed">
              Select a book to compare its line against our model. <span className="text-[#a78bfa] font-medium">Pinnacle</span> is shown as the sharp reference — it has the lowest vig (built-in fee) in the industry, so its implied probabilities are the most efficient.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-x-4 gap-y-1 pt-1">
              <p className="text-[11px] text-gray-600 leading-snug">
                <span className="text-gray-400 font-medium">Vig</span> — the bookmaker&apos;s built-in margin. If you add both sides&apos; implied probabilities they sum to more than 100% — that excess is the vig (typically 4–8% at US books, ~2% at Pinnacle).
              </p>
              <p className="text-[11px] text-gray-600 leading-snug">
                <span className="text-gray-400 font-medium">Mkt %</span> — the book&apos;s implied probability with the vig removed, so both sides sum to 100%. This is the market&apos;s &quot;true&quot; estimate of each team&apos;s win probability.
              </p>
              <p className="text-[11px] text-gray-600 leading-snug">
                <span className="text-gray-400 font-medium">EV</span> — expected profit per $1 wagered if our model is right. Positive EV is rare and does not guarantee a win. Our models have no demonstrated market edge — treat this as informational only.
              </p>
            </div>
          </div>

          {/* Book selector */}
          <div className="flex flex-wrap gap-2">
            {availableBooks.map((key) => (
              <button
                key={key}
                onClick={() => setSelectedBook(key)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border ${
                  selectedBook === key
                    ? key === "pinnacle"
                      ? "bg-[#a78bfa]/20 text-[#a78bfa] border-[#a78bfa]/40"
                      : "bg-[#10b981]/15 text-[#10b981] border-[#10b981]/30"
                    : "bg-transparent text-gray-500 border-[#262626] hover:border-[#333] hover:text-gray-300"
                }`}
              >
                {BOOK_LABELS[key] ?? key}
                {key === "pinnacle" && (
                  <span className="ml-1 text-[9px] font-bold uppercase tracking-widest opacity-70">sharp</span>
                )}
              </button>
            ))}
          </div>

          {/* Odds freshness timestamp */}
          {oddsTimeLabel && (
            <p className="text-[11px] text-gray-600">
              Lines as of <span className="text-gray-500">{oddsTimeLabel}</span> — updated hourly
            </p>
          )}

          {/* H2H comparison */}
          {hasH2H && selH2H && (
            <div>
              <p className="mb-2 text-xs font-semibold text-gray-500 uppercase tracking-widest">Moneyline</p>
              <div className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] overflow-hidden">
                {/* Column headers */}
                <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-x-4 px-4 py-2 border-b border-[#1a1a1a]">
                  <span className="text-[10px] text-gray-600 uppercase tracking-wider">Side</span>
                  <span className="text-[10px] text-gray-600 text-right">Price</span>
                  <span className="text-[10px] text-gray-600 text-right">
                    <MetricTip label="Mkt %" tip="The book's implied win probability after removing their built-in margin (vig). Both sides sum to 100%." />
                  </span>
                  <span className="text-[10px] text-gray-600 text-right">Model %</span>
                  <span className="text-[10px] text-gray-600 text-right">
                    <MetricTip label="EV" tip="Expected value per $1 wagered: model P × (decimal odds − 1) − (1 − model P). Negative after vig is the norm." />
                  </span>
                </div>

                {/* Home row */}
                {selH2H.home_american != null ? (
                  <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-x-4 px-4 py-2.5 border-b border-[#1a1a1a]">
                    <span className="text-xs text-gray-300 truncate">{homeFullName} (home)</span>
                    <span className={`text-xs font-mono font-semibold text-right ${(selH2H.home_american ?? 0) < 0 ? "text-[#f59e0b]" : "text-[#10b981]"}`}>
                      {fmtAmerican(selH2H.home_american)}
                    </span>
                    <span className="text-xs font-mono text-gray-400 text-right">{fmtPct(selH2H.market_bet_pct_home)}</span>
                    <span className="text-xs font-mono text-gray-300 text-right">{fmtPct(selH2H.model_prob_home)}</span>
                    <span className={`text-xs font-mono font-semibold text-right ${evColor(selH2H.ev_home)}`}>
                      {fmtEV(selH2H.ev_home)}
                    </span>
                  </div>
                ) : (
                  <div className="px-4 py-2.5 border-b border-[#1a1a1a]">
                    <span className="text-xs text-gray-600">No line available from {BOOK_LABELS[selectedBook] ?? selectedBook}</span>
                  </div>
                )}

                {/* Away row */}
                {selH2H.away_american != null && selH2H.model_prob_home != null && (
                  <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-x-4 px-4 py-2.5">
                    <span className="text-xs text-gray-300 truncate">{awayFullName} (away)</span>
                    <span className={`text-xs font-mono font-semibold text-right ${(selH2H.away_american ?? 0) < 0 ? "text-[#f59e0b]" : "text-[#10b981]"}`}>
                      {fmtAmerican(selH2H.away_american)}
                    </span>
                    <span className="text-xs font-mono text-gray-400 text-right">
                      {selH2H.market_bet_pct_home != null ? fmtPct(1 - selH2H.market_bet_pct_home) : "—"}
                    </span>
                    <span className="text-xs font-mono text-gray-300 text-right">
                      {fmtPct(1 - selH2H.model_prob_home)}
                    </span>
                    {(() => {
                      const awayDec = selH2H.away_decimal
                      const awayModelP = selH2H.model_prob_home != null ? 1 - selH2H.model_prob_home : null
                      const awayEV = awayDec != null && awayModelP != null
                        ? awayModelP * (awayDec - 1) - (1 - awayModelP) : null
                      return (
                        <span className={`text-xs font-mono font-semibold text-right ${evColor(awayEV)}`}>
                          {fmtEV(awayEV)}
                        </span>
                      )
                    })()}
                  </div>
                )}
              </div>

              {/* Pinnacle reference (always shown when selected book ≠ Pinnacle) */}
              {selectedBook !== "pinnacle" && pinnacleH2H?.home_american != null && (
                <div className="mt-2 rounded-lg border border-[#a78bfa]/20 bg-[#a78bfa]/5 px-4 py-3">
                  <p className="text-[10px] text-[#a78bfa] font-semibold uppercase tracking-widest mb-2">Pinnacle (sharp reference)</p>
                  <div className="flex flex-wrap gap-x-6 gap-y-1">
                    <span className="text-xs text-gray-400">
                      {homeFullName}: <span className="font-mono">{fmtAmerican(pinnacleH2H.home_american)}</span>
                      {pinnacleH2H.market_bet_pct_home != null && (
                        <span className="text-gray-600 ml-1">({fmtPct(pinnacleH2H.market_bet_pct_home)} no-vig)</span>
                      )}
                    </span>
                    <span className="text-xs text-gray-400">
                      {awayFullName}: <span className="font-mono">{fmtAmerican(pinnacleH2H.away_american)}</span>
                      {pinnacleH2H.market_bet_pct_home != null && (
                        <span className="text-gray-600 ml-1">({fmtPct(1 - pinnacleH2H.market_bet_pct_home)} no-vig)</span>
                      )}
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Totals comparison */}
          {hasTotals && selTotals && (
            <div>
              <div className="mb-2 flex items-center gap-2">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-widest">Totals</p>
                {selTotals.model_prob_over == null && (
                  <span className="text-[10px] text-gray-600 italic">market lines only · model probs unavailable</span>
                )}
              </div>
              <div className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] overflow-hidden">
                <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-x-4 px-4 py-2 border-b border-[#1a1a1a]">
                  <span className="text-[10px] text-gray-600 uppercase tracking-wider">Side</span>
                  <span className="text-[10px] text-gray-600 text-right">Price</span>
                  <span className="text-[10px] text-gray-600 text-right">
                    <MetricTip label="Mkt %" tip="The book's implied over/under probability after removing their built-in margin (vig). Both sides sum to 100%." />
                  </span>
                  <span className="text-[10px] text-gray-600 text-right">
                    <MetricTip label="Model %" tip="Our model P(over/under) computed at THIS book's total line via NegBin CDF — not the consensus line." />
                  </span>
                  <span className="text-[10px] text-gray-600 text-right">
                    <MetricTip label="EV" tip="Expected value per $1: model P × (decimal − 1) − (1 − model P). Negative after vig is normal." />
                  </span>
                </div>

                {selTotals.line != null ? (
                  <>
                    {/* Over row */}
                    <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-x-4 px-4 py-2.5 border-b border-[#1a1a1a]">
                      <span className="text-xs text-gray-300">Over {selTotals.line?.toFixed(1)}</span>
                      <span className={`text-xs font-mono font-semibold text-right ${(selTotals.over_american ?? 0) < 0 ? "text-[#f59e0b]" : "text-[#10b981]"}`}>
                        {fmtAmerican(selTotals.over_american)}
                      </span>
                      <span className="text-xs font-mono text-gray-400 text-right">{fmtPct(selTotals.market_bet_pct_over)}</span>
                      <span className="text-xs font-mono text-gray-300 text-right">{fmtPct(selTotals.model_prob_over)}</span>
                      <span className={`text-xs font-mono font-semibold text-right ${evColor(selTotals.ev_over)}`}>
                        {fmtEV(selTotals.ev_over)}
                      </span>
                    </div>
                    {/* Under row */}
                    <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-x-4 px-4 py-2.5">
                      <span className="text-xs text-gray-300">
                        Under {selTotals.line?.toFixed(1)}
                        {selTotals.p_push != null && selTotals.p_push > 0.001 && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span className="ml-1 text-gray-600 cursor-help text-[10px]">
                                (push {fmtPct(selTotals.p_push)})
                              </span>
                            </TooltipTrigger>
                            <TooltipContent side="top" className="max-w-[230px] text-xs leading-relaxed">
                              Integer total line — model assigns {fmtPct(selTotals.p_push)} probability of an exact push (total = {selTotals.line}).
                            </TooltipContent>
                          </Tooltip>
                        )}
                      </span>
                      <span className={`text-xs font-mono font-semibold text-right ${(selTotals.under_american ?? 0) < 0 ? "text-[#f59e0b]" : "text-[#10b981]"}`}>
                        {fmtAmerican(selTotals.under_american)}
                      </span>
                      <span className="text-xs font-mono text-gray-400 text-right">
                        {selTotals.market_bet_pct_over != null ? fmtPct(1 - selTotals.market_bet_pct_over) : "—"}
                      </span>
                      <span className="text-xs font-mono text-gray-300 text-right">{fmtPct(selTotals.model_prob_under)}</span>
                      <span className={`text-xs font-mono font-semibold text-right ${evColor(selTotals.ev_under)}`}>
                        {fmtEV(selTotals.ev_under)}
                      </span>
                    </div>
                  </>
                ) : (
                  <div className="px-4 py-2.5">
                    <span className="text-xs text-gray-600">No totals line available from {BOOK_LABELS[selectedBook] ?? selectedBook}</span>
                  </div>
                )}
              </div>

              {/* Model total runs annotation */}
              {bookOdds.pred_total_runs != null && (
                <p className="mt-1.5 text-[10px] text-gray-600">
                  Model projected total: {bookOdds.pred_total_runs.toFixed(1)} runs — P(over) is recomputed at each book&apos;s own line.
                </p>
              )}

              {/* Pinnacle reference for totals */}
              {selectedBook !== "pinnacle" && pinnacleTotals?.line != null && (
                <div className="mt-2 rounded-lg border border-[#a78bfa]/20 bg-[#a78bfa]/5 px-4 py-3">
                  <p className="text-[10px] text-[#a78bfa] font-semibold uppercase tracking-widest mb-2">Pinnacle (sharp reference)</p>
                  <div className="flex flex-wrap gap-x-6 gap-y-1">
                    <span className="text-xs text-gray-400">
                      Line: <span className="font-mono">{pinnacleTotals.line.toFixed(1)}</span>
                    </span>
                    <span className="text-xs text-gray-400">
                      Over: <span className="font-mono">{fmtAmerican(pinnacleTotals.over_american)}</span>
                      {pinnacleTotals.market_bet_pct_over != null && (
                        <span className="text-gray-600 ml-1">({fmtPct(pinnacleTotals.market_bet_pct_over)} no-vig)</span>
                      )}
                    </span>
                    <span className="text-xs text-gray-400">
                      Under: <span className="font-mono">{fmtAmerican(pinnacleTotals.under_american)}</span>
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}


// ---------------------------------------------------------------------------
// CollapsibleSection
// ---------------------------------------------------------------------------

function CollapsibleSection({
  title,
  children,
  defaultOpen = true,
}: {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="rounded-xl border border-[#262626] bg-[#141414] overflow-hidden"
    >
      <CollapsibleTrigger asChild>
        <button className="w-full flex items-center justify-between px-6 py-4 hover:bg-[#1a1a1a] transition-colors text-left">
          <span className="flex items-center gap-2.5">
            <span className="w-1 h-5 rounded-full bg-[#10b981] shrink-0" />
            <span className="text-base font-bold text-white">{title}</span>
          </span>
          <ChevronDown
            className={`h-4 w-4 text-gray-500 transition-transform duration-200 shrink-0 ${open ? "rotate-180" : ""}`}
          />
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="px-6 pb-5">{children}</div>
      </CollapsibleContent>
    </Collapsible>
  )
}

// ---------------------------------------------------------------------------
// MetricTip — label with optional tooltip
// ---------------------------------------------------------------------------

function MetricTip({ label, tip }: { label: string; tip?: string }) {
  if (!tip) return <span>{label}</span>
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex items-center gap-1 cursor-help">
          {label}
          <Info className="h-3 w-3 text-gray-600" />
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-[230px] text-xs leading-relaxed">
        {tip}
      </TooltipContent>
    </Tooltip>
  )
}

// ---------------------------------------------------------------------------
// ZScoreBar — umpire/contextual z-score visual
// ---------------------------------------------------------------------------

function ZScoreBar({ label, value, tip, invertColor = false }: {
  label: string
  value: number | null | undefined
  tip?: string
  invertColor?: boolean
}) {
  const pct = value != null ? Math.min(Math.abs(value) / 2, 1) * 50 : 0
  const isPositive = (value ?? 0) >= 0
  const colorClass = value == null
    ? "bg-gray-700"
    : (invertColor ? !isPositive : isPositive)
      ? "bg-[#10b981]"
      : "bg-[#f87171]"
  const label2 = value == null ? "n/a"
    : Math.abs(value) < 0.3 ? "avg"
    : Math.abs(value) < 0.8 ? (isPositive ? "slightly above avg" : "slightly below avg")
    : Math.abs(value) < 1.5 ? (isPositive ? "above avg" : "below avg")
    : (isPositive ? "well above avg" : "well below avg")

  return (
    <div className="py-2 border-b border-[#1e1e1e] last:border-0">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-gray-400"><MetricTip label={label} tip={tip} /></span>
        <span className="text-xs text-gray-500 font-mono">
          {value != null ? (value >= 0 ? "+" : "") + value.toFixed(2) : "—"}
          {" "}<span className="text-gray-600 font-normal">{label2}</span>
        </span>
      </div>
      <div className="relative h-1.5 bg-[#1e1e1e] rounded-full overflow-hidden">
        <div className="absolute top-0 bottom-0 left-1/2 w-px bg-[#333]" />
        {value != null && (
          <div
            className={`absolute top-0 bottom-0 rounded-full ${colorClass}`}
            style={isPositive
              ? { left: "50%", width: `${pct}%` }
              : { right: "50%", width: `${pct}%` }
            }
          />
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// BettingBar — public betting ticket% / money% visual
// ---------------------------------------------------------------------------

function BettingBar({ homeLabel, awayLabel, homePct, awayPct, tip }: {
  homeLabel: string
  awayLabel: string
  homePct: number | null | undefined
  awayPct: number | null | undefined
  tip?: string
}) {
  if (homePct == null && awayPct == null) return null
  const h = homePct ?? 50
  const a = awayPct ?? 50
  return (
    <div className="py-2 border-b border-[#1e1e1e] last:border-0">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs text-gray-300">{homeLabel}</span>
        <span className="text-xs text-gray-400"><MetricTip label="" tip={tip} /></span>
        <span className="text-xs text-gray-300">{awayLabel}</span>
      </div>
      <div className="flex h-2 rounded-full overflow-hidden bg-[#1e1e1e]">
        <div className="bg-[#10b981] transition-all" style={{ width: `${h}%` }} />
        <div className="bg-[#f87171] transition-all flex-1" />
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-xs font-mono text-gray-500">{h.toFixed(0)}%</span>
        <span className="text-xs font-mono text-gray-500">{a.toFixed(0)}%</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CompareRow — side-by-side stat with color coding + optional tooltip
// ---------------------------------------------------------------------------

function CompareRow({
  label,
  home,
  away,
  lowerBetter = false,
  fmt = (n: number) => n.toFixed(3),
  tip,
}: {
  label: string
  home: number | null | undefined
  away: number | null | undefined
  lowerBetter?: boolean
  fmt?: (n: number) => string
  tip?: string
}) {
  function sideColor(a: number | null | undefined, b: number | null | undefined): string {
    if (a == null || b == null) return "text-gray-500"
    if (a === b) return "text-gray-400"
    const better = lowerBetter ? a < b : a > b
    return better ? "text-[#10b981]" : "text-[#f87171]"
  }
  return (
    <div className="grid grid-cols-3 items-center gap-2 py-2 border-b border-[#1e1e1e] last:border-0">
      <span className={`text-xs text-center font-mono ${sideColor(home, away)}`}>
        {home != null ? fmt(home) : "—"}
      </span>
      <span className="text-xs text-gray-400 text-center font-medium">
        <MetricTip label={label} tip={tip} />
      </span>
      <span className={`text-xs text-center font-mono ${sideColor(away, home)}`}>
        {away != null ? fmt(away) : "—"}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function PickDetailPage() {
  const { accessToken, email } = useAuth()
  const params = useParams()
  const gamePk = Number(params.game_pk)

  const { data, isLoading, isError } = useQuery<GameDetailData>({
    queryKey: ["pick-detail", gamePk, accessToken],
    queryFn: () => apiFetch(`/picks/${gamePk}/detail`, {}, accessToken),
    staleTime: 5 * 60 * 1000,
    enabled: !!accessToken && !!gamePk,
  })

  // A0.4.32 — per-book odds comparison (separate query; all 6 books in one payload)
  const { data: bookOdds } = useQuery<BookOddsComparison>({
    queryKey: ["book-odds", gamePk, accessToken],
    queryFn: () => apiFetch(`/picks/${gamePk}/odds-comparison`, {}, accessToken),
    staleTime: 15 * 60 * 1000,
    enabled: !!accessToken && !!gamePk,
  })

  const [selectedBook, setSelectedBook] = useState<string>("pinnacle")

  const picks = data?.picks ?? []
  const firstPick = picks[0]

  useEffect(() => {
    if (firstPick) {
      posthog.capture("pick_detail_viewed", {
        game_pk: gamePk,
        home_team: firstPick.home_team,
        away_team: firstPick.away_team,
        markets: picks.map((p) => p.market_type),
      })
    }
  }, [gamePk, firstPick])

  const homeFullName = data?.home_team_name ?? firstPick?.home_team ?? "Home"
  const awayFullName = data?.away_team_name ?? firstPick?.away_team ?? "Away"
  const homeAbbr = normalizeTeam(firstPick?.home_team ?? "")
  const awayAbbr = normalizeTeam(firstPick?.away_team ?? "")
  const showAbbr = homeAbbr && awayAbbr && (homeAbbr !== homeFullName || awayAbbr !== awayFullName)

  const gameTime = firstPick ? fmtGameTime(firstPick.game_start_utc) : null
  const predictedAt = firstPick?.predicted_at
    ? (() => {
        const iso = firstPick.predicted_at!.endsWith("Z") ? firstPick.predicted_at! : firstPick.predicted_at! + "Z"
        const d = new Date(iso)
        return isNaN(d.getTime()) ? null : d.toLocaleString(undefined, {
          month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short",
        })
      })()
    : null
  const score = data?.game_score
  const isCompleted = score?.status === "Final"

  function fmtRecord(w: number | null, l: number | null): string | null {
    if (w == null || l == null) return null
    return `${w}-${l}`
  }
  const starters = data?.starters
  const bov = data?.bovada_lines
  const feats = data?.team_features
  const lineups = data?.lineups
  const wx = data?.weather
  const pb = data?.public_betting
  const lm = data?.line_movement
  const ump = data?.umpire
  const ctx = data?.game_context

  function teamLogo(abbrev: string): string {
    return `https://a.espncdn.com/i/teamlogos/mlb/500/${espnLogoPath(abbrev)}.png`
  }
  function playerPhoto(id: number | null): string | null {
    if (!id) return null
    return `https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png/w_213,q_auto:best/v1/people/${id}/headshot/67/current`
  }
  function fmtPyth(pct: number | null | undefined, residual: number | null | undefined): string | null {
    if (pct == null) return null
    const pStr = `Pyth ${(pct * 100).toFixed(0)}%`
    if (residual == null || Math.abs(residual) < 0.02) return pStr
    return `${pStr} (${residual > 0 ? "lucky" : "unlucky"})`
  }

  return (
    <AuthGuard>
      <div className="min-h-screen bg-[#0a0a0a] font-sans">
        <Nav authenticated userEmail={email} />

        <main className="mx-auto max-w-6xl px-4 py-8 space-y-4">

          <Link
            href="/dashboard"
            className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
          >
            <ChevronLeft className="h-4 w-4" />
            Back to Dashboard
          </Link>

          {isLoading ? (
            <div className="space-y-4 animate-pulse">
              {/* Game header skeleton */}
              <div className="rounded-xl border border-[#262626] bg-[#141414] px-6 py-5 space-y-3">
                <div className="flex items-center gap-3">
                  <div className="h-8 w-8 rounded bg-[#262626]" />
                  <div className="h-6 w-48 rounded bg-[#262626]" />
                  <div className="h-5 w-8 rounded bg-[#262626]" />
                  <div className="h-8 w-8 rounded bg-[#262626]" />
                  <div className="h-6 w-48 rounded bg-[#262626]" />
                </div>
                <div className="flex gap-3 pt-1">
                  <div className="h-4 w-32 rounded bg-[#262626]" />
                  <div className="h-4 w-24 rounded bg-[#262626]" />
                  <div className="h-4 w-28 rounded bg-[#262626]" />
                </div>
              </div>
              {/* Picks skeleton */}
              <div className="rounded-xl border border-[#262626] bg-[#141414] px-6 py-5 space-y-3">
                <div className="h-4 w-24 rounded bg-[#262626]" />
                <div className="grid grid-cols-4 gap-3">
                  {[1,2,3,4].map(i => <div key={i} className="h-16 rounded bg-[#262626]" />)}
                </div>
              </div>
              {/* Starters skeleton */}
              <div className="rounded-xl border border-[#262626] bg-[#141414] px-6 py-5 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="h-4 w-36 rounded bg-[#262626]" />
                  <div className="h-4 w-4 rounded bg-[#262626]" />
                </div>
                <div className="grid grid-cols-2 gap-6 pt-1">
                  {[1,2].map(i => (
                    <div key={i} className="space-y-2">
                      <div className="flex items-center gap-2">
                        <div className="h-12 w-12 rounded-full bg-[#262626]" />
                        <div className="h-4 w-32 rounded bg-[#262626]" />
                      </div>
                      <div className="h-3 w-full rounded bg-[#262626]" />
                      <div className="h-3 w-3/4 rounded bg-[#262626]" />
                    </div>
                  ))}
                </div>
              </div>
              {/* Team performance + context skeletons */}
              {[1,2,3].map(i => (
                <div key={i} className="rounded-xl border border-[#262626] bg-[#141414] px-6 py-4 flex items-center justify-between">
                  <div className="h-4 w-40 rounded bg-[#262626]" />
                  <div className="h-4 w-4 rounded bg-[#262626]" />
                </div>
              ))}
            </div>
          ) : isError ? (
            <div className="rounded-xl border border-[#262626] bg-[#141414] px-6 py-10 text-center">
              <p className="text-sm text-gray-500 mb-4">Could not load pick data. Try refreshing.</p>
              <Link href="/dashboard" className="text-sm text-[#10b981] hover:underline">Return to Dashboard</Link>
            </div>
          ) : !firstPick ? (
            <div className="rounded-xl border border-[#262626] bg-[#141414] px-6 py-10 text-center">
              <p className="text-sm text-gray-500 mb-4">No data found for this game.</p>
              <Link href="/dashboard" className="text-sm text-[#10b981] hover:underline">Return to Dashboard</Link>
            </div>
          ) : (
            <>
              {/* ============================================================
                  1. Game header — always visible, not collapsible
              ============================================================ */}
              <div className="rounded-xl border border-[#262626] bg-[#141414] px-6 py-5">
                {/* Full team names with logos, pre-game records, Pythagorean */}
                <h1 className="text-2xl font-bold tracking-tight text-white leading-snug flex flex-wrap items-center gap-x-2 gap-y-1">
                  {awayAbbr && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={teamLogo(awayAbbr)}
                      alt={awayAbbr}
                      width={32}
                      height={32}
                      className="rounded shrink-0"
                      onError={(e) => { (e.target as HTMLImageElement).style.display = "none" }}
                    />
                  )}
                  <span>
                    {awayFullName}
                    {fmtRecord(score?.away_wins ?? null, score?.away_losses ?? null) && (
                      <span className="ml-1.5 text-sm font-normal text-gray-500">
                        ({fmtRecord(score?.away_wins ?? null, score?.away_losses ?? null)}
                        {fmtPyth(score?.away_pyth_pct, score?.away_pyth_residual) && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span className="ml-1 cursor-help text-gray-600">· {fmtPyth(score?.away_pyth_pct, score?.away_pyth_residual)}</span>
                            </TooltipTrigger>
                            <TooltipContent side="top" className="max-w-[230px] text-xs leading-relaxed">
                              Pythagorean win expectation based on 30-day runs scored vs allowed. Positive residual (actual &gt; Pyth) may indicate luck; negative may indicate an underperforming team.
                            </TooltipContent>
                          </Tooltip>
                        )}
                        )
                      </span>
                    )}
                  </span>
                  <span className="text-gray-500">@</span>
                  {homeAbbr && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={teamLogo(homeAbbr)}
                      alt={homeAbbr}
                      width={32}
                      height={32}
                      className="rounded shrink-0"
                      onError={(e) => { (e.target as HTMLImageElement).style.display = "none" }}
                    />
                  )}
                  <span>
                    {homeFullName}
                    {fmtRecord(score?.home_wins ?? null, score?.home_losses ?? null) && (
                      <span className="ml-1.5 text-sm font-normal text-gray-500">
                        ({fmtRecord(score?.home_wins ?? null, score?.home_losses ?? null)}
                        {fmtPyth(score?.home_pyth_pct, score?.home_pyth_residual) && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span className="ml-1 cursor-help text-gray-600">· {fmtPyth(score?.home_pyth_pct, score?.home_pyth_residual)}</span>
                            </TooltipTrigger>
                            <TooltipContent side="top" className="max-w-[230px] text-xs leading-relaxed">
                              Pythagorean win expectation based on 30-day runs scored vs allowed. Positive residual (actual &gt; Pyth) may indicate luck; negative may indicate an underperforming team.
                            </TooltipContent>
                          </Tooltip>
                        )}
                        )
                      </span>
                    )}
                  </span>
                </h1>

                <div className="mt-1 mb-4 flex flex-wrap items-center gap-3">
                  {showAbbr && (
                    <span className="text-sm text-gray-500 font-mono">{awayAbbr} @ {homeAbbr}</span>
                  )}
                  {gameTime && (
                    <span className="text-sm text-gray-500">{gameTime}</span>
                  )}
                  {predictedAt && (
                    <span className="text-xs text-gray-600">Predicted {predictedAt}</span>
                  )}
                  {score?.status === "Final" && score.home_score != null && score.away_score != null && (
                    <Badge className="bg-gray-800 text-gray-300 border border-[#262626] text-xs">
                      Final: {awayAbbr || "Away"} {score.away_score} — {homeAbbr || "Home"} {score.home_score}
                    </Badge>
                  )}
                  {score?.status === "Live" && score.home_score != null && score.away_score != null && (
                    <Badge className="bg-[#ef4444]/20 text-[#ef4444] border border-[#ef4444]/30 text-xs">
                      Live: {awayAbbr || "Away"} {score.away_score} — {homeAbbr || "Home"} {score.home_score}
                    </Badge>
                  )}
                </div>

                <div className="flex flex-col gap-3">
                  {picks.map((pick) => (
                    <div
                      key={pick.market_type}
                      className="flex flex-col gap-2 rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-4 py-3"
                    >
                      {/* Market badge + edge + conviction */}
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline" className="border-[#262626] text-gray-400 text-xs font-medium">
                          {marketLabel(pick)}
                        </Badge>
                        <Badge className="bg-[#10b981]/15 text-[#10b981] border border-[#10b981]/30 text-xs font-semibold">
                          Edge {formatEdge(pick.edge ?? 0)}
                        </Badge>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Badge className={`text-xs font-bold uppercase tracking-widest cursor-default ${convictionBadgeClass(pick.game_conviction_score ?? 0)}`}>
                              {convictionLabel(pick.game_conviction_score ?? 0)}
                            </Badge>
                          </TooltipTrigger>
                          <TooltipContent side="top" className="max-w-[240px] text-xs leading-relaxed">
                            Model conviction (early) — {pick.gate_signals_met ?? 0}/5 gate signals active today (criteria 2–5 are off; only criterion 1 fires). Score: {((pick.game_conviction_score ?? 0) * 100).toFixed(0)}/100. This is a confidence signal, not a bet recommendation.
                          </TooltipContent>
                        </Tooltip>
                      </div>

                      {/* Prob / totals details */}
                      <div className="flex flex-col items-start gap-0.5 sm:items-end">
                        {pick.market_type === "h2h" ? (() => {
                          const isAway = pick.pick_side === "away"
                          const modelP = isAway ? 1 - (pick.model_prob ?? 0) : (pick.model_prob ?? 0)
                          const mktP = isAway ? 1 - (pick.bovada_devig_prob ?? 0) : (pick.bovada_devig_prob ?? 0)
                          const teamLabel = isAway ? (pick.away_team ?? "Away") : (pick.home_team ?? "Home")
                          return (
                            <>
                              <p className="text-xs text-gray-500">
                                <span className="text-gray-400">{teamLabel} win —</span>{" "}
                                Model <span className="font-mono text-white">{(modelP * 100).toFixed(1)}%</span>
                                {" "}· Market <span className="font-mono text-gray-400">{(mktP * 100).toFixed(1)}%</span>
                              </p>
                              {pick.model_total_runs != null && (
                                <p className="text-xs text-gray-500">
                                  Model total:{" "}
                                  <span className="font-mono text-gray-300">{pick.model_total_runs.toFixed(1)} runs</span>
                                  {pick.market_total_line != null && (
                                    <> · Line <span className="font-mono text-gray-500">{pick.market_total_line.toFixed(1)}</span></>
                                  )}
                                </p>
                              )}
                            </>
                          )
                        })() : (() => {
                          const isUnder = pick.pick_side === "under"
                          const modelP = isUnder ? 1 - (pick.model_prob ?? 0) : (pick.model_prob ?? 0)
                          const mktP = isUnder ? 1 - (pick.bovada_devig_prob ?? 0) : (pick.bovada_devig_prob ?? 0)
                          const direction = isUnder ? "under" : "over"
                          return (
                            <>
                              {pick.model_total_runs != null && (
                                <p className="text-xs text-gray-500">
                                  Model total:{" "}
                                  <span className="font-mono text-white">{pick.model_total_runs.toFixed(1)} runs</span>
                                  {pick.market_total_line != null && (
                                    <> · Line <span className="font-mono text-gray-500">{pick.market_total_line.toFixed(1)}</span></>
                                  )}
                                </p>
                              )}
                              <p className="text-xs text-gray-500">
                                Model <span className="font-mono text-gray-300">{(modelP * 100).toFixed(1)}%</span>
                                {" "}{direction} · Market <span className="font-mono text-gray-400">{(mktP * 100).toFixed(1)}%</span>
                              </p>
                            </>
                          )
                        })()}
                      </div>

                      {/* Win-probability CI band — h2h only */}
                      {pick.market_type === "h2h" && pick.win_prob_ci_low != null && pick.win_prob_ci_high != null && (() => {
                        const isAway = pick.pick_side === "away"
                        const ciLow = isAway ? 1 - pick.win_prob_ci_high! : pick.win_prob_ci_low!
                        const ciHigh = isAway ? 1 - pick.win_prob_ci_low! : pick.win_prob_ci_high!
                        const modelP = isAway ? 1 - (pick.model_prob ?? 0) : (pick.model_prob ?? 0)
                        const mktP = isAway ? 1 - (pick.bovada_devig_prob ?? 0) : (pick.bovada_devig_prob ?? 0)
                        const halfWidth = pick.win_prob_ci_width != null ? (pick.win_prob_ci_width * 50).toFixed(1) : null
                        return (
                          <div className="border-t border-[#1e1e1e] pt-2 mt-1">
                            <div className="flex items-center justify-between mb-1.5">
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span className="text-xs font-medium text-gray-500 cursor-help inline-flex items-center gap-1">
                                    80% win-probability CI
                                    <Info className="h-3 w-3" />
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent side="top" className="max-w-[260px] text-xs leading-relaxed">
                                  Green bar = 80% credible interval for the model&apos;s win-probability estimate. White line = model point estimate. Orange marker = Bovada implied probability. Narrower bar = higher model confidence. Morning rows may show a narrower CI (imputed pre-lineup matrix) — prefer the post-lineup row when available.
                                </TooltipContent>
                              </Tooltip>
                              <span className="text-xs font-mono text-gray-500">
                                {(ciLow * 100).toFixed(1)}%–{(ciHigh * 100).toFixed(1)}%
                                {halfWidth && <span className="ml-1.5 text-gray-600">±{halfWidth}pp</span>}
                              </span>
                            </div>
                            <div className="relative h-4 bg-[#1e1e1e] rounded-full overflow-hidden">
                              <div
                                className="absolute top-0 bottom-0 bg-[#10b981]/30 rounded-sm"
                                style={{ left: `${ciLow * 100}%`, width: `${(ciHigh - ciLow) * 100}%` }}
                              />
                              <div
                                className="absolute top-0 bottom-0 w-0.5 bg-[#f59e0b]"
                                style={{ left: `${mktP * 100}%` }}
                              />
                              <div
                                className="absolute top-0 bottom-0 w-0.5 bg-white"
                                style={{ left: `${modelP * 100}%` }}
                              />
                            </div>
                            <div className="flex items-center gap-4 mt-1.5">
                              <span className="text-xs text-gray-500 inline-flex items-center gap-1">
                                <span className="inline-block h-1.5 w-3 bg-white rounded-full" /> Model {(modelP * 100).toFixed(1)}%
                              </span>
                              <span className="text-xs text-gray-500 inline-flex items-center gap-1">
                                <span className="inline-block h-1.5 w-1.5 rounded-full bg-[#f59e0b]" /> Bovada {(mktP * 100).toFixed(1)}%
                              </span>
                            </div>
                          </div>
                        )
                      })()}
                    </div>
                  ))}
                </div>
              </div>

              {/* ============================================================
                  1b. Why this pick — narrative + model reasoning (Story 30.15)
              ============================================================ */}
              {(data?.pick_narrative || data?.pick_explanation) && (() => {
                const expl = data.pick_explanation
                const narrative = data.pick_narrative
                const tier = expl?.served_tier
                // Determine primary market for driver view
                const primaryMarket = firstPick?.market_type ?? "h2h"
                return (
                  <>
                    {narrative && (
                      <div className="rounded-xl border border-[#262626] bg-[#141414] overflow-hidden">
                        <div className="px-6 py-4 border-b border-[#1e1e1e] flex items-center justify-between gap-3">
                          <span className="flex items-center gap-2.5">
                            <span className="w-1 h-5 rounded-full bg-[#10b981] shrink-0" />
                            <span className="text-base font-bold text-white">Why this pick</span>
                          </span>
                          <ServedTierBadge tier={tier} />
                        </div>
                        <div className="px-6 py-4">
                          <p className="text-sm leading-relaxed text-gray-400">{narrative}</p>
                        </div>
                      </div>
                    )}

                    {expl && (
                      <CollapsibleSection title="Model reasoning" defaultOpen={false}>
                        <PickExplanationSection
                          explanation={expl}
                          marketType={primaryMarket}
                        />
                      </CollapsibleSection>
                    )}
                  </>
                )
              })()}

              {/* ============================================================
                  2. Bovada Lines
              ============================================================ */}
              {bov && (bov.h2h || bov.totals) && (
                <CollapsibleSection title="Bovada Lines">
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-4 py-3">
                      <p className="mb-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Moneyline</p>
                      {bov.h2h ? (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-sm text-gray-300">{homeFullName}</span>
                            <span className={`font-mono text-sm font-semibold ${(bov.h2h.home_american ?? 0) < 0 ? "text-[#f59e0b]" : "text-[#10b981]"}`}>
                              {fmtAmerican(bov.h2h.home_american)}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-sm text-gray-300">{awayFullName}</span>
                            <span className={`font-mono text-sm font-semibold ${(bov.h2h.away_american ?? 0) < 0 ? "text-[#f59e0b]" : "text-[#10b981]"}`}>
                              {fmtAmerican(bov.h2h.away_american)}
                            </span>
                          </div>
                        </div>
                      ) : (
                        <p className="text-xs text-gray-600">Not available</p>
                      )}
                    </div>

                    <div className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-4 py-3">
                      <p className="mb-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Over / Under</p>
                      {bov.totals ? (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-sm text-gray-300">
                              Over {bov.totals.line != null ? bov.totals.line.toFixed(1) : ""}
                            </span>
                            <span className={`font-mono text-sm font-semibold ${(bov.totals.over_american ?? 0) < 0 ? "text-[#f59e0b]" : "text-[#10b981]"}`}>
                              {fmtAmerican(bov.totals.over_american)}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-sm text-gray-300">
                              Under {bov.totals.line != null ? bov.totals.line.toFixed(1) : ""}
                            </span>
                            <span className={`font-mono text-sm font-semibold ${(bov.totals.under_american ?? 0) < 0 ? "text-[#f59e0b]" : "text-[#10b981]"}`}>
                              {fmtAmerican(bov.totals.under_american)}
                            </span>
                          </div>
                        </div>
                      ) : (
                        <p className="text-xs text-gray-600">Not available</p>
                      )}
                    </div>
                  </div>
                </CollapsibleSection>
              )}

              {/* ============================================================
                  2b. A0.4.32 — Book Odds Comparison
              ============================================================ */}
              {bookOdds && (bookOdds.h2h.length > 0 || bookOdds.totals.length > 0) && (
                <BookOddsSection
                  bookOdds={bookOdds}
                  homeFullName={homeFullName}
                  awayFullName={awayFullName}
                  selectedBook={selectedBook}
                  setSelectedBook={setSelectedBook}
                />
              )}

              {/* ============================================================
                  3. Starters — label changes for completed games
              ============================================================ */}
              {starters && (starters.home || starters.away) && (
                <CollapsibleSection title={isCompleted ? "Starting Pitchers" : "Probable Starters"}>
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    {(["home", "away"] as const).map((side) => {
                      const sp = starters[side]
                      const teamName = side === "home" ? homeFullName : awayFullName
                      const hand = side === "home" ? feats?.home?.starter_hand : feats?.away?.starter_hand
                      const showPrior = (sp?.prior_starts ?? 0) > 0 && (sp?.starts ?? 0) < 8
                      return (
                        <div key={side} className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-4 py-3">
                          <p className="mb-1 text-xs font-medium text-gray-500 uppercase tracking-wider">{teamName}</p>
                          <div className="mb-3 flex items-center gap-3">
                            {sp?.pitcher_id && playerPhoto(sp.pitcher_id) && (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img
                                src={playerPhoto(sp.pitcher_id)!}
                                alt={sp.name ?? ""}
                                width={48}
                                height={48}
                                className="rounded-full object-cover bg-[#1e1e1e] shrink-0"
                                onError={(e) => { (e.target as HTMLImageElement).style.display = "none" }}
                              />
                            )}
                            <div>
                              <p className="text-base font-semibold text-white flex items-center gap-2 flex-wrap">
                                {sp?.name ?? "TBD"}
                                {sp?.is_opener && (
                                  <span className="text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30 px-1.5 py-0.5 rounded uppercase tracking-widest">
                                    Opener
                                  </span>
                                )}
                                {hand && (
                                  <span className="text-xs font-normal text-gray-500 bg-[#1e1e1e] px-1.5 py-0.5 rounded">
                                    {hand === "L" ? "LHP" : hand === "R" ? "RHP" : hand}
                                  </span>
                                )}
                              </p>
                            </div>
                          </div>

                          {sp?.name ? (
                            <>
                              {/* Current season stats */}
                              <p className="mb-1.5 text-[10px] font-semibold text-gray-600 uppercase tracking-widest">
                                {sp.is_opener
                                  ? `Recent outings (opener role)${sp.starts != null ? ` · ${sp.starts}` : ""}`
                                  : `${sp.season ?? "Current"} Season${sp.starts != null ? ` · ${sp.starts} GS` : ""}`
                                }
                              </p>
                              {(sp.starts ?? 0) > 0 ? (
                                <div className="grid grid-cols-3 gap-2 text-center">
                                  <div>
                                    <p className="text-lg font-bold text-white font-mono">{fmtStat(sp.ra9, 2)}</p>
                                    <p className="text-xs text-gray-500">RA/9</p>
                                  </div>
                                  <div>
                                    <p className="text-lg font-bold text-white font-mono">{fmtStat(sp.whip, 2)}</p>
                                    <p className="text-xs text-gray-500">WHIP</p>
                                  </div>
                                  <div>
                                    <p className="text-lg font-bold text-white font-mono">
                                      {sp.k_pct != null ? `${sp.k_pct.toFixed(1)}%` : "—"}
                                    </p>
                                    <p className="text-xs text-gray-500">K%</p>
                                  </div>
                                </div>
                              ) : (
                                <p className="text-xs text-gray-600 mb-1">No starts this season yet</p>
                              )}

                              {/* Prior season — shown when current sample is sparse (< 8 GS) */}
                              {showPrior && (
                                <div className="mt-3 pt-3 border-t border-[#1e1e1e]">
                                  <p className="mb-1.5 text-[10px] font-semibold text-gray-600 uppercase tracking-widest">
                                    {sp.prior_season} Season (full) · {sp.prior_starts} GS
                                  </p>
                                  <div className="grid grid-cols-3 gap-2 text-center">
                                    <div>
                                      <p className="text-base font-semibold text-gray-400 font-mono">{fmtStat(sp.prior_ra9, 2)}</p>
                                      <p className="text-xs text-gray-600">RA/9</p>
                                    </div>
                                    <div>
                                      <p className="text-base font-semibold text-gray-400 font-mono">{fmtStat(sp.prior_whip, 2)}</p>
                                      <p className="text-xs text-gray-600">WHIP</p>
                                    </div>
                                    <div>
                                      <p className="text-base font-semibold text-gray-400 font-mono">
                                        {sp.prior_k_pct != null ? `${sp.prior_k_pct.toFixed(1)}%` : "—"}
                                      </p>
                                      <p className="text-xs text-gray-600">K%</p>
                                    </div>
                                  </div>
                                </div>
                              )}
                            </>
                          ) : (
                            <p className="text-xs text-gray-600">Starter not announced</p>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </CollapsibleSection>
              )}

              {/* ============================================================
                  4. Batting Lineups
              ============================================================ */}
              {lineups && (lineups.home.length > 0 || lineups.away.length > 0) && (
                <CollapsibleSection title={isCompleted ? "Batting Lineups & Box Score" : "Batting Lineups"}>
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    {(["home", "away"] as const).map((side) => {
                      const players = lineups[side]
                      const teamName = side === "home" ? homeFullName : awayFullName
                      const hasBoxScore = players.some((p) => p.game_h != null)
                      return (
                        <div key={side}>
                          <p className="mb-2 text-xs font-medium text-gray-500 uppercase tracking-wider">{teamName}</p>
                          {players.length === 0 ? (
                            <p className="text-xs text-gray-600">Lineup not yet announced</p>
                          ) : (
                            <div className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] overflow-hidden">
                              {/* Header */}
                              {hasBoxScore ? (
                                <div className="grid grid-cols-[1.5rem_1fr_auto_auto_auto_auto_auto] gap-x-3 px-3 py-1.5 border-b border-[#1e1e1e]">
                                  <span className="text-[10px] text-gray-600 text-center">#</span>
                                  <span className="text-[10px] text-gray-600">Name</span>
                                  <span className="text-[10px] text-gray-600 text-right">H/AB</span>
                                  <span className="text-[10px] text-gray-600 text-right">K</span>
                                  <span className="text-[10px] text-gray-600 text-right">BB</span>
                                  <span className="text-[10px] text-gray-600 text-right">HR</span>
                                  <span className="text-[10px] text-gray-600 text-right">xwOBA</span>
                                </div>
                              ) : (
                                <div className="grid grid-cols-[1.5rem_1fr_auto_auto_auto] gap-x-3 px-3 py-1.5 border-b border-[#1e1e1e]">
                                  <span className="text-[10px] text-gray-600 text-center">#</span>
                                  <span className="text-[10px] text-gray-600">Name</span>
                                  <span className="text-[10px] text-gray-600 text-right">Pos</span>
                                  <span className="text-[10px] text-gray-600 text-right">OPS</span>
                                  <span className="text-[10px] text-gray-600 text-right">xwOBA</span>
                                </div>
                              )}
                              {/* Rows */}
                              {players.map((p) => (
                                hasBoxScore ? (
                                  <div
                                    key={p.slot}
                                    className="grid grid-cols-[1.5rem_1fr_auto_auto_auto_auto_auto] gap-x-3 px-3 py-2 border-b border-[#1a1a1a] last:border-0 hover:bg-[#111111] transition-colors"
                                  >
                                    <span className="text-xs text-gray-600 text-center">{p.slot}</span>
                                    <span className="text-xs text-gray-200 truncate">{p.player_name ?? "—"}</span>
                                    <span className="text-xs font-mono text-gray-300 text-right">
                                      {p.game_h != null && p.game_ab != null ? `${p.game_h}/${p.game_ab}` : "—"}
                                    </span>
                                    <span className="text-xs font-mono text-gray-400 text-right">{p.game_k ?? "—"}</span>
                                    <span className="text-xs font-mono text-gray-400 text-right">{p.game_bb ?? "—"}</span>
                                    <span className={`text-xs font-mono text-right ${(p.game_hr ?? 0) > 0 ? "text-[#f59e0b]" : "text-gray-400"}`}>
                                      {p.game_hr ?? "—"}
                                    </span>
                                    <span className="text-xs font-mono text-gray-400 text-right">
                                      {p.game_xwoba != null ? p.game_xwoba.toFixed(3) : "—"}
                                    </span>
                                  </div>
                                ) : (
                                  <div
                                    key={p.slot}
                                    className="grid grid-cols-[1.5rem_1fr_auto_auto_auto] gap-x-3 px-3 py-2 border-b border-[#1a1a1a] last:border-0 hover:bg-[#111111] transition-colors"
                                  >
                                    <span className="text-xs text-gray-600 text-center">{p.slot}</span>
                                    <span className="text-xs text-gray-200 truncate">{p.player_name ?? "—"}</span>
                                    <span className="text-xs text-gray-500 text-right">{p.position ?? "—"}</span>
                                    <span className="text-xs font-mono text-gray-400 text-right">
                                      {p.season_ops != null ? p.season_ops.toFixed(3) : "—"}
                                    </span>
                                    <span className="text-xs font-mono text-gray-400 text-right">
                                      {p.season_xwoba != null ? p.season_xwoba.toFixed(3) : "—"}
                                    </span>
                                  </div>
                                )
                              ))}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </CollapsibleSection>
              )}

              {/* ============================================================
                  5. Team Performance
              ============================================================ */}
              {feats && (feats.home || feats.away) && (
                <CollapsibleSection title="Team Performance">
                  <p className="mb-3 text-xs text-gray-500">
                    Rolling stats used as model inputs. <span className="text-[#10b981]">Green</span> = better side for that metric.
                  </p>

                  {/* Column headers */}
                  <div className="grid grid-cols-3 gap-2 pb-2 mb-1">
                    <span className="text-xs font-semibold text-gray-300 text-center truncate">{homeAbbr || "Home"}</span>
                    <span />
                    <span className="text-xs font-semibold text-gray-300 text-center truncate">{awayAbbr || "Away"}</span>
                  </div>

                  {/* Offense */}
                  <p className="mt-2 mb-1 text-xs font-semibold text-gray-500 uppercase tracking-widest">Offense (30d)</p>
                  <CompareRow
                    label="wOBA" home={feats.home?.off_woba_30d} away={feats.away?.off_woba_30d}
                    fmt={n => n.toFixed(3)}
                    tip="Weighted On-Base Average over the last 30 days. Weights each outcome (BB, 1B, 2B, 3B, HR) by its run value. League average ≈ .320. Higher is better."
                  />
                  <CompareRow
                    label="xwOBA" home={feats.home?.off_xwoba_30d} away={feats.away?.off_xwoba_30d}
                    fmt={n => n.toFixed(3)}
                    tip="Expected Weighted On-Base Average over the last 30 days — based on quality of contact (exit velocity, launch angle), not outcomes. Compares to wOBA: team with xwOBA > wOBA has been getting unlucky (expect regression upward); xwOBA < wOBA has been getting lucky (expect regression downward)."
                  />
                  <CompareRow
                    label="R/G" home={feats.home?.off_runs_per_game_30d} away={feats.away?.off_runs_per_game_30d}
                    fmt={n => n.toFixed(2)}
                    tip="Runs scored per game over the last 30 days."
                  />

                  {/* Starting Pitcher */}
                  <p className="mt-4 mb-1 text-xs font-semibold text-gray-500 uppercase tracking-widest">Starting Pitcher (30d)</p>
                  <CompareRow
                    label="xwOBA Against" home={feats.home?.starter_xwoba_against_30d} away={feats.away?.starter_xwoba_against_30d}
                    lowerBetter fmt={n => n.toFixed(3)}
                    tip="Expected wOBA allowed by the starter over the last 30 days, based on quality of contact (exit velo, launch angle). Lower is better."
                  />
                  <CompareRow
                    label="K%" home={feats.home?.starter_k_pct_30d} away={feats.away?.starter_k_pct_30d}
                    fmt={n => `${(n * 100).toFixed(1)}%`}
                    tip="Strikeout rate — percentage of plate appearances ending in a strikeout over the last 30 starts."
                  />

                  {/* Lineup handedness matchup vs opposing starter */}
                  <p className="mt-4 mb-1 text-xs font-semibold text-gray-500 uppercase tracking-widest">Lineup vs Opp Starter (Handedness)</p>
                  <CompareRow
                    label="Platoon xwOBA" home={feats.home?.lineup_vs_sp_xwoba_adj} away={feats.away?.lineup_vs_sp_xwoba_adj}
                    fmt={n => n.toFixed(3)}
                    tip="Each batter's expected wOBA split based on whether they're facing a same-hand or opposite-hand pitcher, then averaged across the lineup. Higher = the lineup has a more favorable handedness matchup against the opposing starter. A lineup of LHB facing a RHP, for example, typically scores higher than the same lineup facing a LHP."
                  />

                  {/* Bullpen */}
                  <p className="mt-4 mb-1 text-xs font-semibold text-gray-500 uppercase tracking-widest">Bullpen (14d)</p>
                  <CompareRow
                    label="xwOBA Against" home={feats.home?.bp_xwoba_against_14d} away={feats.away?.bp_xwoba_against_14d}
                    lowerBetter fmt={n => n.toFixed(3)}
                    tip="Expected wOBA allowed by the bullpen over the last 14 days. Lower is better."
                  />
                  <CompareRow
                    label="IP" home={feats.home?.bp_innings_pitched_14d} away={feats.away?.bp_innings_pitched_14d}
                    lowerBetter fmt={n => n.toFixed(1)}
                    tip="Total innings pitched by the bullpen in the last 14 days. More innings = less rest. Lower is better (fresher bullpen)."
                  />

                  {/* Schedule */}
                  <p className="mt-4 mb-1 text-xs font-semibold text-gray-500 uppercase tracking-widest">Schedule</p>
                  <CompareRow
                    label="Days Rest" home={feats.home?.days_rest} away={feats.away?.days_rest}
                    fmt={n => String(Math.round(n))}
                    tip="Days since the team's last game. More rest generally favors the team."
                  />

                  {/* Context */}
                  {(feats.park_run_factor != null || feats.elo_diff != null) && (
                    <>
                      <p className="mt-4 mb-1 text-xs font-semibold text-gray-500 uppercase tracking-widest">Context</p>
                      {feats.park_run_factor != null && (
                        <div className="grid grid-cols-3 items-center gap-2 py-2 border-b border-[#1e1e1e]">
                          <span className="text-xs text-center font-mono text-gray-300">
                            {feats.park_run_factor.toFixed(3)}
                          </span>
                          <span className="text-xs text-gray-400 text-center font-medium">
                            <MetricTip
                              label="Runs/G at Park (3yr)"
                              tip="Average total runs scored per game at this park over the last 3 years (both teams combined). League average ≈ 8.9. Higher means a more run-scoring environment — e.g., Coors Field is typically 11+."
                            />
                          </span>
                          <span className="text-xs text-center font-mono text-gray-600">—</span>
                        </div>
                      )}
                      {feats.elo_diff != null && (
                        <div className="grid grid-cols-3 items-center gap-2 py-2">
                          <span className={`text-xs text-center font-mono font-semibold ${feats.elo_diff >= 0 ? "text-[#10b981]" : "text-[#f87171]"}`}>
                            {feats.elo_diff >= 0 ? "+" : ""}{Math.round(feats.elo_diff)}
                          </span>
                          <span className="text-xs text-gray-400 text-center font-medium">
                            <MetricTip
                              label="ELO Diff (Home − Away)"
                              tip="ELO is a chess-derived rating system where each team starts the season near 1500 and gains/loses points based on game outcomes, weighted by opponent strength. The difference shown here is Home ELO minus Away ELO — positive means the home team is rated stronger entering this game. Typical in-season range: ±100–200 points."
                            />
                          </span>
                          <span className="text-xs text-center font-mono text-gray-600">—</span>
                        </div>
                      )}
                    </>
                  )}
                </CollapsibleSection>
              )}

              {/* ============================================================
                  6. Umpire
              ============================================================ */}
              {ump?.name && (
                <CollapsibleSection title="Home Plate Umpire">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <p className="text-base font-semibold text-white">{ump.name}</p>
                      {ump.games_sample != null && (
                        <p className="text-xs text-gray-600 mt-0.5">Based on {ump.games_sample} games (career)</p>
                      )}
                    </div>
                  </div>
                  <ZScoreBar
                    label="K Rate Tendency"
                    value={ump.k_pct_zscore}
                    tip="How this umpire's strikeout rate compares to the league average umpire (z-score). Positive = more Ks than average. Relevant for totals — high-K umpires tend to suppress offense."
                  />
                  <ZScoreBar
                    label="Run Impact"
                    value={ump.run_impact_zscore}
                    tip="This umpire's overall run-environment impact vs average (z-score). Positive = games tend to be higher-scoring. Negative = games tend to be lower-scoring. Strong signal for totals bets."
                  />
                  <ZScoreBar
                    label="BB Rate Tendency"
                    value={ump.bb_pct_zscore}
                    tip="How this umpire's walk rate compares to average (z-score). Positive = more walks than average — a larger zone tends to suppress walks."
                    invertColor={true}
                  />
                </CollapsibleSection>
              )}

              {/* ============================================================
                  7. Market Action — public betting + line movement
              ============================================================ */}
              {(pb || lm) && (
                <CollapsibleSection title="Market Action">
                  {pb && (
                    <>
                      <p className="mb-3 text-xs font-semibold text-gray-500 uppercase tracking-widest">Public Betting (Moneyline)</p>
                      <BettingBar
                        homeLabel={homeAbbr || "Home"}
                        awayLabel={awayAbbr || "Away"}
                        homePct={pb.home_ml_money_pct}
                        awayPct={pb.away_ml_money_pct}
                        tip="Percentage of total money wagered on each side. Money % reflects sharp/large bettors more than ticket %."
                      />
                      <BettingBar
                        homeLabel={`${homeAbbr || "Home"} tickets`}
                        awayLabel={`${awayAbbr || "Away"} tickets`}
                        homePct={pb.home_ml_ticket_pct}
                        awayPct={pb.away_ml_ticket_pct}
                        tip="Percentage of total bets (tickets) placed on each side. Ticket % reflects the public/recreational bettor crowd."
                      />
                      {pb.ml_sharp_signal != null && (
                        <div className="mt-3 flex items-center gap-2 py-2 border-b border-[#1e1e1e]">
                          <span className="text-xs text-gray-400">ML Sharp Signal</span>
                          <span className={`ml-auto text-xs font-mono font-semibold ${Math.abs(pb.ml_sharp_signal) < 5 ? "text-gray-500" : pb.ml_sharp_signal > 0 ? "text-[#10b981]" : "text-[#f87171]"}`}>
                            {pb.ml_sharp_signal > 0 ? "+" : ""}{pb.ml_sharp_signal.toFixed(0)}
                          </span>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="h-3 w-3 text-gray-600 cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent side="top" className="max-w-[230px] text-xs leading-relaxed">
                              Action Network sharp signal: positive = sharp money on the home team, negative = on the away team. High absolute value (±20+) with divergence from public tickets is a meaningful signal.
                            </TooltipContent>
                          </Tooltip>
                        </div>
                      )}

                      {(pb.over_ticket_pct != null || pb.over_money_pct != null) && (
                        <>
                          <p className="mt-4 mb-3 text-xs font-semibold text-gray-500 uppercase tracking-widest">Public Betting (Totals)</p>
                          <BettingBar
                            homeLabel="Over"
                            awayLabel="Under"
                            homePct={pb.over_money_pct}
                            awayPct={pb.under_money_pct}
                            tip="Percentage of total money on Over vs Under."
                          />
                          <BettingBar
                            homeLabel="Over tickets"
                            awayLabel="Under tickets"
                            homePct={pb.over_ticket_pct}
                            awayPct={pb.under_ticket_pct}
                            tip="Percentage of bet count (tickets) on Over vs Under."
                          />
                          {pb.total_sharp_signal != null && (
                            <div className="mt-3 flex items-center gap-2 py-2">
                              <span className="text-xs text-gray-400">Totals Sharp Signal</span>
                              <span className={`ml-auto text-xs font-mono font-semibold ${Math.abs(pb.total_sharp_signal) < 5 ? "text-gray-500" : pb.total_sharp_signal > 0 ? "text-[#10b981]" : "text-[#f87171]"}`}>
                                {pb.total_sharp_signal > 0 ? "+" : ""}{pb.total_sharp_signal.toFixed(0)}
                              </span>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Info className="h-3 w-3 text-gray-600 cursor-help" />
                                </TooltipTrigger>
                                <TooltipContent side="top" className="max-w-[230px] text-xs leading-relaxed">
                                  Positive = sharp money on the Over, negative = on the Under.
                                </TooltipContent>
                              </Tooltip>
                            </div>
                          )}
                          <p className="mt-2 text-[10px] text-gray-600">Public betting data available from 2026-05-07 onward.</p>
                        </>
                      )}
                    </>
                  )}

                  {lm && (lm.open_home_win_prob != null || lm.open_total_line != null) && (
                    <>
                      <p className="mt-4 mb-3 text-xs font-semibold text-gray-500 uppercase tracking-widest">Bovada Line Movement</p>
                      {lm.open_home_win_prob != null && lm.pregame_home_win_prob != null && (
                        <div className="grid grid-cols-3 items-center gap-2 py-2 border-b border-[#1e1e1e]">
                          <span className="text-xs font-mono text-gray-400 text-center">{(lm.open_home_win_prob * 100).toFixed(1)}%</span>
                          <span className="text-xs text-gray-500 text-center">
                            <MetricTip label="Home Win Prob" tip="Bovada implied home win probability (de-vigged). Opening line vs closing line; movement shows which side took sharp action." />
                          </span>
                          <span className={`text-xs font-mono text-center font-semibold ${
                            (lm.h2h_line_movement ?? 0) > 0.01 ? "text-[#10b981]" :
                            (lm.h2h_line_movement ?? 0) < -0.01 ? "text-[#f87171]" : "text-gray-400"
                          }`}>
                            {(lm.pregame_home_win_prob * 100).toFixed(1)}%
                            {lm.h2h_line_movement != null && (
                              <span className="text-[10px] ml-1">
                                ({lm.h2h_line_movement >= 0 ? "+" : ""}{(lm.h2h_line_movement * 100).toFixed(1)}pp)
                              </span>
                            )}
                          </span>
                        </div>
                      )}
                      {lm.open_total_line != null && (
                        <div className="grid grid-cols-3 items-center gap-2 py-2">
                          <span className="text-xs font-mono text-gray-400 text-center">{lm.open_total_line.toFixed(1)}</span>
                          <span className="text-xs text-gray-500 text-center">
                            <MetricTip label="Total Line" tip="Bovada total line (runs). Opening vs closing. Line moving up = sportsbook (or sharp money) expects more scoring; down = less." />
                          </span>
                          <span className={`text-xs font-mono text-center font-semibold ${
                            (lm.total_line_movement ?? 0) > 0.1 ? "text-[#f87171]" :
                            (lm.total_line_movement ?? 0) < -0.1 ? "text-[#10b981]" : "text-gray-400"
                          }`}>
                            {lm.pregame_total_line != null ? lm.pregame_total_line.toFixed(1) : "—"}
                            {lm.total_line_movement != null && Math.abs(lm.total_line_movement) > 0.05 && (
                              <span className="text-[10px] ml-1">
                                ({lm.total_line_movement >= 0 ? "+" : ""}{lm.total_line_movement.toFixed(1)})
                              </span>
                            )}
                          </span>
                        </div>
                      )}
                    </>
                  )}
                </CollapsibleSection>
              )}

              {/* ============================================================
                  8. Weather
              ============================================================ */}
              {wx && (
                <CollapsibleSection title="Weather">
                  {wx.is_dome ? (
                    <div className="flex items-center gap-2">
                      <span className="text-xs bg-[#1e1e1e] text-gray-400 px-2 py-1 rounded-full">Dome / Indoor</span>
                      <span className="text-xs text-gray-600">Weather not a factor for this game.</span>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                        {wx.temp_f != null && (
                          <div className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2.5 text-center">
                            <p className={`text-lg font-bold font-mono ${wx.temp_f > 85 ? "text-[#f87171]" : wx.temp_f < 55 ? "text-sky-400" : "text-white"}`}>
                              {Math.round(wx.temp_f)}°F
                            </p>
                            <p className="text-[10px] text-gray-600 mt-0.5">Temperature</p>
                          </div>
                        )}
                        {wx.wind_speed_mph != null && (
                          <div className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2.5 text-center">
                            <p className="text-lg font-bold font-mono text-white">{wx.wind_speed_mph.toFixed(0)} mph</p>
                            <p className="text-[10px] text-gray-600 mt-0.5">Wind Speed</p>
                          </div>
                        )}
                        {wx.wind_component_mph != null && (
                          <div className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2.5 text-center">
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <div className="cursor-help">
                                  <p className={`text-lg font-bold font-mono ${wx.wind_component_mph > 5 ? "text-[#f87171]" : wx.wind_component_mph < -5 ? "text-[#10b981]" : "text-gray-400"}`}>
                                    {wx.wind_component_mph > 0 ? "+" : ""}{wx.wind_component_mph.toFixed(1)} mph
                                  </p>
                                  <p className="text-[10px] text-gray-600 mt-0.5">Wind Out/In</p>
                                </div>
                              </TooltipTrigger>
                              <TooltipContent side="top" className="max-w-[230px] text-xs leading-relaxed">
                                Wind component blowing toward the outfield (+) or infield (−) relative to home plate. Positive (out) = ball carries, favors offense/over. Negative (in) = headwind, suppresses scoring.
                              </TooltipContent>
                            </Tooltip>
                          </div>
                        )}
                      </div>
                      {wx.observation_type && (
                        <p className="text-[10px] text-gray-600">
                          {wx.observation_type === "forecast_pregame" ? "Pre-game forecast" :
                           wx.observation_type === "observed_at_first_pitch" ? "Observed at first pitch" :
                           wx.observation_type === "forecast_intraday" ? "Intraday forecast" :
                           wx.observation_type}
                        </p>
                      )}
                    </div>
                  )}
                </CollapsibleSection>
              )}

              {/* ============================================================
                  9. Recent Form + H2H
              ============================================================ */}
              {ctx && (ctx.home_form || ctx.away_form || ctx.h2h) && (
                <CollapsibleSection title="Recent Form & Head-to-Head">
                  {(ctx.home_form || ctx.away_form) && (
                    <>
                      <div className="grid grid-cols-2 gap-4 mb-4">
                        {(["home", "away"] as const).map((side) => {
                          const form = ctx[`${side}_form` as "home_form" | "away_form"]
                          const teamName = side === "home" ? homeAbbr || "Home" : awayAbbr || "Away"
                          if (!form) return null
                          const l5Short = form.l5_games != null && form.l5_games < 5
                          const l10Short = form.l10_games != null && form.l10_games < 10
                          return (
                            <div key={side}>
                              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">{teamName}</p>
                              <div className="space-y-1.5">
                                {form.l5_wins != null && form.l5_losses != null && (
                                  <div className="flex items-center justify-between">
                                    <span className="text-xs text-gray-500">
                                      Last 5
                                      {l5Short && form.l5_games != null && (
                                        <Tooltip>
                                          <TooltipTrigger asChild>
                                            <span className="ml-1 text-gray-600 cursor-help">(L{form.l5_games})</span>
                                          </TooltipTrigger>
                                          <TooltipContent>Only {form.l5_games} games with a decided winner available before this game.</TooltipContent>
                                        </Tooltip>
                                      )}
                                    </span>
                                    <span className={`text-xs font-mono font-semibold ${form.l5_wins > form.l5_losses ? "text-[#10b981]" : form.l5_wins < form.l5_losses ? "text-[#f87171]" : "text-gray-400"}`}>
                                      {form.l5_wins}-{form.l5_losses}
                                    </span>
                                  </div>
                                )}
                                {form.l10_wins != null && form.l10_losses != null && (
                                  <div className="flex items-center justify-between">
                                    <span className="text-xs text-gray-500">
                                      Last 10
                                      {l10Short && form.l10_games != null && (
                                        <Tooltip>
                                          <TooltipTrigger asChild>
                                            <span className="ml-1 text-gray-600 cursor-help">(L{form.l10_games})</span>
                                          </TooltipTrigger>
                                          <TooltipContent>Only {form.l10_games} games with a decided winner available before this game.</TooltipContent>
                                        </Tooltip>
                                      )}
                                    </span>
                                    <span className={`text-xs font-mono font-semibold ${form.l10_wins > form.l10_losses ? "text-[#10b981]" : form.l10_wins < form.l10_losses ? "text-[#f87171]" : "text-gray-400"}`}>
                                      {form.l10_wins}-{form.l10_losses}
                                    </span>
                                  </div>
                                )}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </>
                  )}

                  {ctx.h2h && ctx.h2h.games_played != null && ctx.h2h.games_played > 0 && (
                    <>
                      <p className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-2">Season Series</p>
                      <div className="rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-4 py-3">
                        <div className="flex items-center justify-between">
                          <div className="text-center">
                            <p className={`text-2xl font-bold font-mono ${(ctx.h2h.home_wins ?? 0) > (ctx.h2h.away_wins ?? 0) ? "text-[#10b981]" : "text-gray-400"}`}>
                              {ctx.h2h.home_wins ?? 0}
                            </p>
                            <p className="text-xs text-gray-500">{homeAbbr || "Home"}</p>
                          </div>
                          <div className="text-center">
                            <p className="text-sm text-gray-600">{ctx.h2h.games_played} games played</p>
                            {ctx.h2h.avg_total_runs != null && (
                              <p className="text-xs text-gray-600 mt-0.5">Avg total: {ctx.h2h.avg_total_runs.toFixed(1)} R</p>
                            )}
                          </div>
                          <div className="text-center">
                            <p className={`text-2xl font-bold font-mono ${(ctx.h2h.away_wins ?? 0) > (ctx.h2h.home_wins ?? 0) ? "text-[#10b981]" : "text-gray-400"}`}>
                              {ctx.h2h.away_wins ?? 0}
                            </p>
                            <p className="text-xs text-gray-500">{awayAbbr || "Away"}</p>
                          </div>
                        </div>
                      </div>
                    </>
                  )}
                </CollapsibleSection>
              )}


              <div className="flex justify-center">
                <ReportDataIssue gamePk={gamePk} />
              </div>

              <p className="pb-8 text-xs leading-relaxed text-gray-600">
                This analysis is generated by a quantitative model and does not constitute financial
                advice. Past performance does not guarantee future results. You are solely responsible
                for any wagers placed.
              </p>
            </>
          )}

        </main>
      </div>
    </AuthGuard>
  )
}
