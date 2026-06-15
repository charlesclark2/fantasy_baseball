"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import posthog from "posthog-js"
import { useQuery } from "@tanstack/react-query"
import { AuthGuard } from "@/components/auth-guard"
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

// ---------------------------------------------------------------------------
// Types matching GameDetailResponse
// ---------------------------------------------------------------------------

type Pick = {
  market_type: string
  model_prob: number | null
  bovada_devig_prob: number | null
  edge: number | null
  game_conviction_score: number | null
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
                      className="flex flex-col gap-2 rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline" className="border-[#262626] text-gray-400 text-xs font-medium">
                          {marketLabel(pick)}
                        </Badge>
                        <Badge className="bg-[#10b981]/15 text-[#10b981] border border-[#10b981]/30 text-xs font-semibold">
                          Edge {formatEdge(pick.edge ?? 0)}
                        </Badge>
                        <Badge className={`text-xs font-bold uppercase tracking-widest ${convictionBadgeClass(pick.game_conviction_score ?? 0)}`}>
                          {convictionLabel(pick.game_conviction_score ?? 0)}
                        </Badge>
                      </div>
                      <div className="flex flex-col items-start sm:items-end gap-0.5">
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
                    </div>
                  ))}
                </div>
              </div>

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
