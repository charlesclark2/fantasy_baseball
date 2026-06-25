"use client"

import { useState, useMemo } from "react"
import { useLocalStorage } from "@/hooks/use-local-storage"
import posthog from "posthog-js"
import { useQuery } from "@tanstack/react-query"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { format } from "date-fns"
import { CalendarIcon, ChevronDown, ChevronUp, ChevronsUpDown, ExternalLink } from "lucide-react"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { AuthGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { Nav } from "@/components/nav"
import { useSelectedDate } from "@/lib/date-context"
import { apiFetch } from "@/lib/api"

import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Calendar } from "@/components/ui/calendar"
import { Skeleton } from "@/components/ui/skeleton"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { normalizeTeam } from "@/lib/teams"

// ---------------------------------------------------------------------------
// API types
// ---------------------------------------------------------------------------
interface EVPick {
  game_pk: number
  game_date: string
  game_start_utc: string | null
  market_type: string
  model_prob: number | null
  bovada_devig_prob: number | null
  edge: number | null
  game_conviction_score: number | null
  lineup_confirmed: boolean | null
  qualified_bet: boolean | null
  home_team: string | null
  away_team: string | null
  kelly_fraction: number | null
  total_line_consensus: number | null
  pred_total_runs: number | null
}

interface EVPicksResponse {
  picks: EVPick[]
  total: number
  is_preliminary?: boolean
}

// E9.11 — line-shopping types
interface LineshoppingPlay {
  game_pk: number
  game_date: string
  game_start_utc: string | null
  home_team: string | null
  away_team: string | null
  market_type: string
  side: string         // "home" | "away" | "over" | "under"
  model_prob: number
  best_book_key: string
  best_book_name: string
  best_american: number
  best_devigged_prob: number
  edge: number
  ev: number | null
  breakeven_american: number | null
  pinnacle_devigged_prob: number | null
}

interface LineshoppingResponse {
  plays: LineshoppingPlay[]
  total: number
  is_preliminary?: boolean
}

// ---------------------------------------------------------------------------
// Sort types — shared across both tables
// ---------------------------------------------------------------------------
type SortKey =
  | "game"
  | "market"
  | "modelProb"    // h2h: sort by model probability
  | "bovadaProb"   // h2h: sort by book probability
  | "predRuns"     // totals: sort by model's projected total
  | "edge"
  | "ev"
  | "rawKelly"
  | "cappedKelly"
  | "stake"

type SortDir = "asc" | "desc"

// ---------------------------------------------------------------------------
// ComputedRow
// ---------------------------------------------------------------------------
interface ComputedRow {
  game_pk: number
  game_date: string | null
  game: string
  time: string
  gameStartUtc: string | null
  market: string
  marketType: string
  side: string
  modelProb: number
  bovadaProb: number
  sideModelDisplay: string
  sideBovadaDisplay: string
  qualified: boolean
  highConviction: boolean
  edge: number          // modelProb - bovadaProb (signed; negative = away/under favored)
  displayEdge: number   // Math.abs(edge) — always positive for display
  ev: number
  rawKelly: number
  cappedKelly: number
  predTotalRuns: number | null
  totalLineConsensus: number | null
  lineupConfirmed: boolean
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function pctRaw(v: number) {
  return `${(v * 100).toFixed(1)}%`
}
function usd(v: number) {
  return `$${v.toFixed(2)}`
}
function fmtEdge(v: number) {
  const clamped = Math.min(v, 1)   // edge is model_prob - market_prob; max meaningful value is 1
  return `+${(clamped * 100).toFixed(1)}%`
}
function fmtEV(v: number) {
  const clamped = Math.max(-2, Math.min(v, 5)) // cap at +500% / -200% to guard against bad odds data
  return `${clamped >= 0 ? "+" : ""}${(clamped * 100).toFixed(1)}%`
}

// ---------------------------------------------------------------------------
// Column header with tooltip
// ---------------------------------------------------------------------------
function ColHeaderTip({ label, tip }: { label: string; tip: string }) {
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="cursor-help border-b border-dotted border-gray-700">{label}</span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[220px] text-center text-xs text-white border-[#262626] bg-[#1a1a1a]">
          {tip}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

function americanOdds(prob: number): string {
  if (prob <= 0 || prob >= 1) return "—"
  if (prob >= 0.5) return String(Math.round(-(prob / (1 - prob)) * 100))
  return `+${Math.round(((1 - prob) / prob) * 100)}`
}

function fmtAmerican(am: number): string {
  return am >= 0 ? `+${am}` : String(am)
}

const LS_BOOK_LABELS: Record<string, string> = {
  betmgm: "BetMGM", caesars: "Caesars", fanduel: "FanDuel",
  draftkings: "DraftKings", fanatics: "Fanatics", bovada: "Bovada",
}

function formatGameTime(isoString: string | null): string {
  if (!isoString) return ""
  const d = new Date(isoString)
  if (isNaN(d.getTime())) return ""
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZoneName: "short" })
}

function computeRow(pick: EVPick, maxKelly: number): ComputedRow {
  const homeTeam = normalizeTeam(pick.home_team ?? "Home")
  const awayTeam = normalizeTeam(pick.away_team ?? "Away")
  const game = `${awayTeam} @ ${homeTeam}`
  const isTotal = pick.market_type === "totals"
  const modelProb = pick.model_prob ?? 0
  const bovadaProb = pick.bovada_devig_prob ?? 0

  // Always compute edge from probabilities; the DB layer4_totals_over_signal is on a
  // different scale and causes >100% display issues when used directly.
  const edge = modelProb - bovadaProb
  const side = isTotal ? (edge >= 0 ? "Over" : "Under") : (edge >= 0 ? "Home" : "Away")

  const lineDisplay = pick.total_line_consensus != null
    ? Number(pick.total_line_consensus).toFixed(1) : "?"
  const market = isTotal
    ? `${side} ${lineDisplay}`
    : `${side === "Home" ? homeTeam : awayTeam} ML`

  // Pick-side perspective: delta from 50% for h2h; raw prob for totals
  let sideModelDisplay: string
  let sideBovadaDisplay: string
  if (isTotal) {
    sideModelDisplay = pctRaw(modelProb)
    sideBovadaDisplay = pctRaw(bovadaProb)
  } else {
    const sideModel = side === "Home" ? modelProb : 1 - modelProb
    const sideBook  = side === "Home" ? bovadaProb : 1 - bovadaProb
    const mDelta = (sideModel - 0.5) * 100
    const bDelta = (sideBook - 0.5) * 100
    sideModelDisplay = `${mDelta >= 0 ? "+" : ""}${mDelta.toFixed(1)}%`
    sideBovadaDisplay = `${bDelta >= 0 ? "+" : ""}${bDelta.toFixed(1)}%`
  }

  // EV and Kelly must be computed from the PICKED side's perspective.
  // DB model_prob / bovada_devig_prob are always the home (h2h) or over (totals) probability.
  // For Away / Under picks the edge is negative, so we flip both to get the correct side.
  const pickedModelProb = edge >= 0 ? modelProb : 1 - modelProb
  const pickedBovadaProb = edge >= 0 ? bovadaProb : 1 - bovadaProb

  const ev = pickedBovadaProb > 0
    ? pickedModelProb * (1 / pickedBovadaProb - 1) - (1 - pickedModelProb)
    : 0

  // Always derive Kelly from picked-side probs. The DB kelly_fraction is stored from the
  // home perspective and is negative for away picks, which produces a $0 stake incorrectly.
  const rawKelly = pickedBovadaProb < 1
    ? ((pickedModelProb - pickedBovadaProb) / (1 - pickedBovadaProb)) * 100
    : 0
  // Only qualified bets get a non-zero stake recommendation.
  const cappedKelly = (pick.qualified_bet ?? false)
    ? Math.min(Math.max(rawKelly, 0), maxKelly)
    : 0

  const highConviction = (pick.game_conviction_score ?? 0) >= 0.8

  // Append T12:00:00 so the date is parsed as local noon, not UTC midnight (avoids day shift)
  const gameDate = format(new Date(pick.game_date + "T12:00:00"), "MMM d")
  const gameTime = formatGameTime(pick.game_start_utc)
  const time = gameTime ? `${gameDate} · ${gameTime}` : gameDate

  return {
    game_pk: pick.game_pk,
    game_date: pick.game_date,
    game, time, gameStartUtc: pick.game_start_utc,
    market, marketType: pick.market_type, side,
    modelProb, bovadaProb, sideModelDisplay, sideBovadaDisplay,
    qualified: pick.qualified_bet ?? false,
    highConviction,
    edge,
    displayEdge: Math.min(Math.abs(edge), 1), // probabilities can't exceed 1
    ev: Math.max(-2, Math.min(ev, 5)),         // guard against degenerate odds data
    rawKelly, cappedKelly,
    predTotalRuns: pick.pred_total_runs ?? null,
    totalLineConsensus: pick.total_line_consensus ?? null,
    lineupConfirmed: pick.lineup_confirmed ?? false,
  }
}

function applySort(rows: ComputedRow[], key: SortKey, dir: SortDir, bankroll: number): ComputedRow[] {
  return [...rows].sort((a, b) => {
    let av: number | string
    let bv: number | string
    switch (key) {
      case "game":        av = a.gameStartUtc ?? "9999-" + a.game; bv = b.gameStartUtc ?? "9999-" + b.game; break
      case "market":      av = a.market;              bv = b.market;              break
      case "modelProb":   av = a.modelProb;           bv = b.modelProb;           break
      case "bovadaProb":  av = a.bovadaProb;          bv = b.bovadaProb;          break
      case "predRuns":    av = a.predTotalRuns ?? -1; bv = b.predTotalRuns ?? -1; break
      case "edge":        av = a.displayEdge;         bv = b.displayEdge;         break
      case "ev":          av = a.ev;                  bv = b.ev;                  break
      case "rawKelly":    av = a.rawKelly;            bv = b.rawKelly;            break
      case "cappedKelly": av = a.cappedKelly;         bv = b.cappedKelly;         break
      case "stake":       av = (a.cappedKelly / 100) * bankroll; bv = (b.cappedKelly / 100) * bankroll; break
      default:            av = a.displayEdge;         bv = b.displayEdge;
    }
    if (typeof av === "string" && typeof bv === "string") {
      return dir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av)
    }
    return dir === "asc" ? (av as number) - (bv as number) : (bv as number) - (av as number)
  })
}

// ---------------------------------------------------------------------------
// Sort icon
// ---------------------------------------------------------------------------
function SortIcon({ col, sortKey, sortDir }: { col: SortKey; sortKey: SortKey; sortDir: SortDir }) {
  if (col !== sortKey) return <ChevronsUpDown className="ml-1 inline h-3 w-3 text-gray-600" />
  return sortDir === "asc"
    ? <ChevronUp className="ml-1 inline h-3 w-3 text-[#10b981]" />
    : <ChevronDown className="ml-1 inline h-3 w-3 text-[#10b981]" />
}

// ---------------------------------------------------------------------------
// Market badge
// ---------------------------------------------------------------------------
function MarketBadge({ type, label }: { type: string; label: string }) {
  const cls = type === "totals"
    ? "bg-teal-950 text-teal-400 border-teal-800"
    : "bg-blue-950 text-blue-400 border-blue-800"
  return (
    <Badge variant="outline" className={cn("text-[10px] font-medium uppercase tracking-wide border px-1.5 py-0", cls)}>
      {label}
    </Badge>
  )
}

// ---------------------------------------------------------------------------
// Capped Kelly cell — tooltip when 0
// ---------------------------------------------------------------------------
function CappedKellyCell({ cappedKelly, rawKelly }: { cappedKelly: number; rawKelly: number }) {
  const display = `${cappedKelly.toFixed(1)}%`
  if (cappedKelly > 0) return <span className="text-sm text-gray-400">{display}</span>
  const reason = rawKelly < 0
    ? "Negative edge — model does not favor this side from a Kelly perspective."
    : "Edge is below Kelly threshold — no stake recommended."
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="cursor-help text-sm text-gray-600 underline decoration-dotted">{display}</span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[200px] text-xs text-center text-white border-[#262626] bg-[#1a1a1a]">{reason}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

// ---------------------------------------------------------------------------
// Log Bet action — confirmation for unqualified bets
// ---------------------------------------------------------------------------
function LogBetAction({ row, onLog }: { row: ComputedRow; onLog: () => void }) {
  if (row.qualified) {
    return (
      <Button variant="outline" size="sm"
        onClick={(e) => { e.stopPropagation(); onLog() }}
        className="h-8 border-[#10b981] bg-transparent px-3 text-xs font-medium text-[#10b981] hover:bg-[#10b98115] hover:text-[#10b981]">
        Log Bet
      </Button>
    )
  }
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="outline" size="sm" onClick={(e) => e.stopPropagation()}
          className="h-8 border-gray-700 bg-transparent px-3 text-xs font-medium text-gray-500 hover:bg-[#1a1a1a] hover:text-gray-300">
          Log Bet
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent className="border-[#262626] bg-[#141414]">
        <AlertDialogHeader>
          <AlertDialogTitle className="text-white">Log unqualified bet?</AlertDialogTitle>
          <AlertDialogDescription className="text-gray-400">
            This market does not meet the model&apos;s qualification threshold. No stake is recommended. Are you sure you want to log this bet?
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel className="border-[#262626] bg-transparent text-gray-400 hover:bg-[#1a1a1a] hover:text-white">Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={onLog} className="bg-[#10b981] text-[#0a0a0a] hover:bg-[#059669]">Log Anyway</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

// ---------------------------------------------------------------------------
// Section divider between qualified and unqualified rows
// ---------------------------------------------------------------------------
function NotRecommendedDivider({ colSpan }: { colSpan: number }) {
  return (
    <TableRow className="border-0 hover:bg-transparent">
      <TableCell colSpan={colSpan} className="px-3 py-2">
        <div className="flex items-center gap-3">
          <div className="h-px flex-1 bg-[#262626]" />
          <span className="text-[10px] font-medium uppercase tracking-widest text-gray-600">Not Recommended</span>
          <div className="h-px flex-1 bg-[#262626]" />
        </div>
      </TableCell>
    </TableRow>
  )
}

// ---------------------------------------------------------------------------
// Skeleton rows
// ---------------------------------------------------------------------------
function SkeletonRows({ cols }: { cols: number }) {
  return (
    <>
      {Array.from({ length: 4 }).map((_, i) => (
        <TableRow key={i} className="border-b border-[#262626]">
          {Array.from({ length: cols }).map((_, j) => (
            <TableCell key={j} className="px-3 py-3">
              <Skeleton className="h-4 w-full bg-[#262626]" />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  )
}

// ---------------------------------------------------------------------------
// Mobile sort pills — shown above card stacks on small screens
// ---------------------------------------------------------------------------
function MobileSortPills({
  sortKey, sortDir, onSort, options,
}: {
  sortKey: SortKey
  sortDir: SortDir
  onSort: (k: SortKey) => void
  options: { key: SortKey; label: string }[]
}) {
  return (
    <div className="mb-3 flex flex-wrap gap-2">
      {options.map(opt => (
        <button
          key={opt.key}
          onClick={() => onSort(opt.key)}
          className={cn(
            "flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
            sortKey === opt.key
              ? "border-[#10b981] bg-[#10b98115] text-[#10b981]"
              : "border-[#262626] bg-[#141414] text-gray-500 active:text-gray-300",
          )}
        >
          {opt.label}
          {sortKey === opt.key && (
            sortDir === "asc"
              ? <ChevronUp className="h-3 w-3" />
              : <ChevronDown className="h-3 w-3" />
          )}
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Mobile skeleton cards
// ---------------------------------------------------------------------------
function SkeletonCards({ count }: { count?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count ?? 4 }).map((_, i) => (
        <div key={i} className="rounded-xl border border-[#262626] bg-[#141414] p-4 space-y-3">
          <Skeleton className="h-4 w-2/3 bg-[#262626]" />
          <Skeleton className="h-4 w-1/3 bg-[#262626]" />
          <div className="grid grid-cols-2 gap-3">
            <Skeleton className="h-8 bg-[#262626]" />
            <Skeleton className="h-8 bg-[#262626]" />
            <Skeleton className="h-8 bg-[#262626]" />
            <Skeleton className="h-8 bg-[#262626]" />
          </div>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Mobile section divider
// ---------------------------------------------------------------------------
function MobileNotRecommendedDivider() {
  return (
    <div className="flex items-center gap-3 py-1">
      <div className="h-px flex-1 bg-[#262626]" />
      <span className="text-[10px] font-medium uppercase tracking-widest text-gray-600">Not Recommended</span>
      <div className="h-px flex-1 bg-[#262626]" />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function EVTrackerPage() {
  const router = useRouter()
  const { selectedDate, setSelectedDate, isoDate } = useSelectedDate()
  const [calOpen, setCalOpen] = useState(false)
  const [bankroll, setBankroll] = useLocalStorage<number>("ev_bankroll", 1000)
  const [maxKelly, setMaxKelly] = useLocalStorage<number>("ev_kelly_cap", 5)

  // Separate sort state per table — default to game time ascending
  const [h2hSort, setH2hSort] = useState<SortKey>("game")
  const [h2hDir, setH2hDir] = useState<SortDir>("asc")
  const [totalsSort, setTotalsSort] = useState<SortKey>("game")
  const [totalsDir, setTotalsDir] = useState<SortDir>("asc")

  const { accessToken, email } = useAuth()

  const { data, isLoading } = useQuery<EVPicksResponse>({
    queryKey: ["picks-ev", isoDate],
    queryFn: () => apiFetch(`/picks/ev?date=${isoDate}`, {}, accessToken),
    staleTime: 5 * 60 * 1000,
  })

  const { data: lsData, isLoading: lsLoading } = useQuery<LineshoppingResponse>({
    queryKey: ["picks-line-shopping", isoDate],
    queryFn: () => apiFetch(`/picks/line-shopping?date=${isoDate}`, {}, accessToken),
    staleTime: 5 * 60 * 1000,
  })

  const allRows = useMemo(() => (data?.picks ?? []).map(p => computeRow(p, maxKelly)), [data, maxKelly])
  const h2hRows = useMemo(() => allRows.filter(r => r.marketType === "h2h"), [allRows])
  const totalsRows = useMemo(() => allRows.filter(r => r.marketType === "totals"), [allRows])

  const sortedH2h = useMemo(() => applySort(h2hRows, h2hSort, h2hDir, bankroll), [h2hRows, h2hSort, h2hDir, bankroll])
  const sortedTotals = useMemo(() => applySort(totalsRows, totalsSort, totalsDir, bankroll), [totalsRows, totalsSort, totalsDir, bankroll])

  const qualifiedCount = allRows.filter(r => r.qualified).length
  const totalCount = allRows.length
  const estDailyEV = allRows.filter(r => r.qualified).reduce((acc, r) => {
    return acc + r.ev * (r.cappedKelly / 100) * bankroll
  }, 0)

  function makeHandleSort(
    currentKey: SortKey, setKey: (k: SortKey) => void,
    currentDir: SortDir, setDir: (d: SortDir) => void,
  ) {
    return (col: SortKey) => {
      if (col === currentKey) {
        // Toggle direction on repeated click — no reset to a different column
        setDir(currentDir === "asc" ? "desc" : "asc")
      } else {
        setKey(col)
        // Time-based columns default asc (earliest first); numeric columns default desc (highest first)
        setDir(col === "game" ? "asc" : "desc")
      }
    }
  }

  const handleH2hSort = makeHandleSort(h2hSort, setH2hSort, h2hDir, setH2hDir)
  const handleTotalsSort = makeHandleSort(totalsSort, setTotalsSort, totalsDir, setTotalsDir)

  function buildLogBetUrl(row: ComputedRow) {
    const params = new URLSearchParams({
      game_pk: String(row.game_pk),
      market: row.market,
      side: row.side,
      modelProb: String(row.modelProb),
      bovadaProb: String(row.bovadaProb),
    })
    if (row.game_date) params.set("game_date", row.game_date)
    return `/bet-log?${params.toString()}`
  }

  // Render rows for a table, inserting the "Not Recommended" divider between
  // qualified and unqualified rows.
  function renderTableBody(
    sorted: ComputedRow[],
    renderRow: (row: ComputedRow) => React.ReactNode,
    dividerColSpan: number,
    emptyMessage: string,
    cols: number,
  ) {
    if (isLoading) return <SkeletonRows cols={cols} />
    if (sorted.length === 0) {
      return (
        <TableRow>
          <TableCell colSpan={cols} className="py-12 text-center text-sm text-gray-500">
            {emptyMessage}
          </TableCell>
        </TableRow>
      )
    }
    const qualified = sorted.filter(r => r.qualified)
    const unqualified = sorted.filter(r => !r.qualified)
    const all = [...qualified, ...unqualified]
    const nodes: React.ReactNode[] = []
    all.forEach((row, i) => {
      if (qualified.length > 0 && unqualified.length > 0 && i === qualified.length) {
        nodes.push(<NotRecommendedDivider key="divider" colSpan={dividerColSpan} />)
      }
      nodes.push(renderRow(row))
    })
    return <>{nodes}</>
  }

  const thCls = "cursor-pointer select-none whitespace-nowrap text-xs font-medium text-gray-500 uppercase tracking-wide hover:text-gray-300 transition-colors px-3 py-3"
  const thNoCls = "select-none whitespace-nowrap text-xs font-medium text-gray-500 uppercase tracking-wide px-3 py-3"

  function renderH2hRow(row: ComputedRow) {
    const stake = (row.cappedKelly / 100) * bankroll
    const isQualified = row.qualified
    const sideProb = row.side === "Home" ? row.bovadaProb : 1 - row.bovadaProb
    return (
      <TableRow
        key={`h2h-${row.game_pk}`}
        onClick={() => {
          posthog.capture("ev_tracker_pick_clicked", {
            game_pk: row.game_pk,
            market_type: row.marketType,
            side: row.side,
            qualified: row.qualified,
            high_conviction: row.highConviction,
          })
          router.push(`/picks/${row.game_pk}`)
        }}
        className={cn(
          "border-b border-[#262626] transition-colors cursor-pointer hover:bg-[#10b98108]",
          !isQualified && "opacity-60",
        )}
      >
        <TableCell className="py-3 pl-4 pr-3">
          <div className="flex items-center gap-1.5">
            <p className="text-sm font-medium text-white">{row.game}</p>
            {row.highConviction && (
              <TooltipProvider delayDuration={150}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="inline-flex items-center rounded px-1 py-0 text-[9px] font-semibold uppercase tracking-wide bg-amber-950 text-amber-400 border border-amber-800 cursor-help">HC</span>
                  </TooltipTrigger>
                  <TooltipContent side="top" className="max-w-[180px] text-center text-xs text-white border-[#262626] bg-[#1a1a1a]">
                    High Conviction — model signals are strong and lineup is confirmed
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </div>
          <p className="text-xs text-gray-500">{row.time}</p>
          <div className="flex items-center gap-1 mt-1">
            <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${row.lineupConfirmed ? "bg-[#10b981]" : "bg-[#f59e0b]"}`} />
            <span className={`text-[10px] font-medium ${row.lineupConfirmed ? "text-[#10b981]" : "text-[#f59e0b]"}`}>
              {row.lineupConfirmed ? "Confirmed" : "Projected"}
            </span>
          </div>
        </TableCell>
        <TableCell className="px-3 py-3">
          <MarketBadge type={row.marketType} label={row.market} />
        </TableCell>
        <TableCell className={cn("px-3 py-3 text-right text-sm font-medium", "text-[#10b981]")}>
          {row.sideModelDisplay}
        </TableCell>
        <TableCell className="px-3 py-3 text-right text-sm text-gray-400">
          {row.sideBovadaDisplay}
        </TableCell>
        <TableCell className="px-3 py-3 text-right text-sm text-gray-500">
          {americanOdds(sideProb)}
        </TableCell>
        <TableCell className={cn("px-3 py-3 text-right text-sm font-semibold", row.displayEdge > 0.01 ? "text-[#10b981]" : "text-gray-500")}>
          {fmtEdge(row.displayEdge)}
        </TableCell>
        <TableCell className={cn("px-3 py-3 text-right text-sm font-semibold", row.ev > 0 ? "text-[#10b981]" : "text-[#ef4444]")}>
          {fmtEV(row.ev)}
        </TableCell>
        <TableCell className="px-3 py-3 text-right text-sm text-gray-400 hidden xl:table-cell">
          {row.rawKelly >= 0 ? `+${row.rawKelly.toFixed(1)}%` : `${row.rawKelly.toFixed(1)}%`}
        </TableCell>
        <TableCell className="px-3 py-3 text-right">
          {isQualified
            ? <CappedKellyCell cappedKelly={row.cappedKelly} rawKelly={row.rawKelly} />
            : <span className="text-sm text-gray-600">—</span>}
        </TableCell>
        <TableCell className={cn("px-3 py-3 text-right text-sm font-medium", isQualified ? "text-[#10b981]" : "text-gray-600")}>
          {isQualified ? usd(stake) : "—"}
        </TableCell>
        <TableCell className="px-3 py-3 text-center">
          <LogBetAction row={row} onLog={() => { posthog.capture("ev_tracker_log_bet_initiated", { game_pk: row.game_pk, market_type: row.marketType, side: row.side, qualified: row.qualified }); router.push(buildLogBetUrl(row)) }} />
        </TableCell>
      </TableRow>
    )
  }

  function renderTotalsRow(row: ComputedRow) {
    const stake = (row.cappedKelly / 100) * bankroll
    const isQualified = row.qualified
    return (
      <TableRow
        key={`totals-${row.game_pk}`}
        onClick={() => {
          posthog.capture("ev_tracker_pick_clicked", {
            game_pk: row.game_pk,
            market_type: row.marketType,
            side: row.side,
            qualified: row.qualified,
            high_conviction: row.highConviction,
          })
          router.push(`/picks/${row.game_pk}`)
        }}
        className={cn(
          "border-b border-[#262626] transition-colors cursor-pointer hover:bg-[#10b98108]",
          !isQualified && "opacity-60",
        )}
      >
        <TableCell className="py-3 pl-4 pr-3">
          <div className="flex items-center gap-1.5">
            <p className="text-sm font-medium text-white">{row.game}</p>
            {row.highConviction && (
              <TooltipProvider delayDuration={150}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="inline-flex items-center rounded px-1 py-0 text-[9px] font-semibold uppercase tracking-wide bg-amber-950 text-amber-400 border border-amber-800 cursor-help">HC</span>
                  </TooltipTrigger>
                  <TooltipContent side="top" className="max-w-[180px] text-center text-xs text-white border-[#262626] bg-[#1a1a1a]">
                    High Conviction — model signals are strong and lineup is confirmed
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </div>
          <p className="text-xs text-gray-500">{row.time}</p>
          <div className="flex items-center gap-1 mt-1">
            <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${row.lineupConfirmed ? "bg-[#10b981]" : "bg-[#f59e0b]"}`} />
            <span className={`text-[10px] font-medium ${row.lineupConfirmed ? "text-[#10b981]" : "text-[#f59e0b]"}`}>
              {row.lineupConfirmed ? "Confirmed" : "Projected"}
            </span>
          </div>
        </TableCell>
        <TableCell className="px-3 py-3">
          <MarketBadge type={row.marketType} label={row.market} />
        </TableCell>
        <TableCell className="px-3 py-3 text-right text-sm font-medium tabular-nums text-[#10b981]">
          {row.predTotalRuns != null ? row.predTotalRuns.toFixed(1) : "—"}
        </TableCell>
        <TableCell className={cn("px-3 py-3 text-right text-sm font-semibold", row.displayEdge > 0.01 ? "text-[#10b981]" : "text-gray-500")}>
          {fmtEdge(row.displayEdge)}
        </TableCell>
        <TableCell className={cn("px-3 py-3 text-right text-sm font-semibold", row.ev > 0 ? "text-[#10b981]" : "text-[#ef4444]")}>
          {fmtEV(row.ev)}
        </TableCell>
        <TableCell className="px-3 py-3 text-right text-sm text-gray-400 hidden xl:table-cell">
          {row.rawKelly >= 0 ? `+${row.rawKelly.toFixed(1)}%` : `${row.rawKelly.toFixed(1)}%`}
        </TableCell>
        <TableCell className="px-3 py-3 text-right">
          {isQualified
            ? <CappedKellyCell cappedKelly={row.cappedKelly} rawKelly={row.rawKelly} />
            : <span className="text-sm text-gray-600">—</span>}
        </TableCell>
        <TableCell className={cn("px-3 py-3 text-right text-sm font-medium", isQualified ? "text-[#10b981]" : "text-gray-600")}>
          {isQualified ? usd(stake) : "—"}
        </TableCell>
        <TableCell className="px-3 py-3 text-center">
          <LogBetAction row={row} onLog={() => { posthog.capture("ev_tracker_log_bet_initiated", { game_pk: row.game_pk, market_type: row.marketType, side: row.side, qualified: row.qualified }); router.push(buildLogBetUrl(row)) }} />
        </TableCell>
      </TableRow>
    )
  }

  // -------------------------------------------------------------------------
  // Mobile card renderers
  // -------------------------------------------------------------------------
  function renderH2hCard(row: ComputedRow) {
    const stake = (row.cappedKelly / 100) * bankroll
    const isQualified = row.qualified
    return (
      <div
        key={`h2h-card-${row.game_pk}`}
        onClick={() => router.push(`/picks/${row.game_pk}`)}
        className={cn(
          "rounded-xl border border-[#262626] bg-[#141414] p-4 transition-colors cursor-pointer active:bg-[#10b98108]",
          !isQualified && "opacity-60",
        )}
      >
        {/* Game header */}
        <div className="mb-2 flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-medium text-white">{row.game}</span>
            {row.highConviction && (
              <span className="inline-flex items-center rounded px-1 py-0 text-[9px] font-semibold uppercase tracking-wide bg-amber-950 text-amber-400 border border-amber-800">HC</span>
            )}
          </div>
          <span className="shrink-0 text-xs text-gray-500">{row.time}</span>
        </div>
        {/* Pick badge */}
        <div className="mb-3">
          <MarketBadge type={row.marketType} label={row.market} />
        </div>
        {/* Stat grid */}
        <div className="mb-3 grid grid-cols-2 gap-x-6 gap-y-2">
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wide text-gray-600">Edge</p>
            <p className={cn("mt-0.5 text-sm font-semibold", row.displayEdge > 0.01 ? "text-[#10b981]" : "text-gray-500")}>
              {fmtEdge(row.displayEdge)}
            </p>
          </div>
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wide text-gray-600">EV</p>
            <p className={cn("mt-0.5 text-sm font-semibold", row.ev > 0 ? "text-[#10b981]" : "text-[#ef4444]")}>
              {fmtEV(row.ev)}
            </p>
          </div>
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wide text-gray-600">Capped Kelly</p>
            <p className="mt-0.5 text-sm text-gray-400">{isQualified ? `${row.cappedKelly.toFixed(1)}%` : "—"}</p>
          </div>
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wide text-gray-600">Stake</p>
            <p className={cn("mt-0.5 text-sm font-medium", isQualified ? "text-[#10b981]" : "text-gray-600")}>
              {isQualified ? usd(stake) : "—"}
            </p>
          </div>
        </div>
        {/* Action */}
        <div className="flex justify-end">
          <LogBetAction row={row} onLog={() => { posthog.capture("ev_tracker_log_bet_initiated", { game_pk: row.game_pk, market_type: row.marketType, side: row.side, qualified: row.qualified }); router.push(buildLogBetUrl(row)) }} />
        </div>
      </div>
    )
  }

  function renderTotalsCard(row: ComputedRow) {
    const stake = (row.cappedKelly / 100) * bankroll
    const isQualified = row.qualified
    return (
      <div
        key={`totals-card-${row.game_pk}`}
        onClick={() => router.push(`/picks/${row.game_pk}`)}
        className={cn(
          "rounded-xl border border-[#262626] bg-[#141414] p-4 transition-colors cursor-pointer active:bg-[#10b98108]",
          !isQualified && "opacity-60",
        )}
      >
        {/* Game header */}
        <div className="mb-2 flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-medium text-white">{row.game}</span>
            {row.highConviction && (
              <span className="inline-flex items-center rounded px-1 py-0 text-[9px] font-semibold uppercase tracking-wide bg-amber-950 text-amber-400 border border-amber-800">HC</span>
            )}
          </div>
          <span className="shrink-0 text-xs text-gray-500">{row.time}</span>
        </div>
        {/* Pick badge + projected runs inline */}
        <div className="mb-3 flex items-center gap-2">
          <MarketBadge type={row.marketType} label={row.market} />
          {row.predTotalRuns != null && (
            <span className="text-xs text-gray-500">
              Proj. <span className="font-medium text-[#10b981]">{row.predTotalRuns.toFixed(1)}</span>
            </span>
          )}
        </div>
        {/* Stat grid */}
        <div className="mb-3 grid grid-cols-2 gap-x-6 gap-y-2">
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wide text-gray-600">Edge</p>
            <p className={cn("mt-0.5 text-sm font-semibold", row.displayEdge > 0.01 ? "text-[#10b981]" : "text-gray-500")}>
              {fmtEdge(row.displayEdge)}
            </p>
          </div>
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wide text-gray-600">EV</p>
            <p className={cn("mt-0.5 text-sm font-semibold", row.ev > 0 ? "text-[#10b981]" : "text-[#ef4444]")}>
              {fmtEV(row.ev)}
            </p>
          </div>
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wide text-gray-600">Capped Kelly</p>
            <p className="mt-0.5 text-sm text-gray-400">{isQualified ? `${row.cappedKelly.toFixed(1)}%` : "—"}</p>
          </div>
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wide text-gray-600">Stake</p>
            <p className={cn("mt-0.5 text-sm font-medium", isQualified ? "text-[#10b981]" : "text-gray-600")}>
              {isQualified ? usd(stake) : "—"}
            </p>
          </div>
        </div>
        {/* Action */}
        <div className="flex justify-end">
          <LogBetAction row={row} onLog={() => { posthog.capture("ev_tracker_log_bet_initiated", { game_pk: row.game_pk, market_type: row.marketType, side: row.side, qualified: row.qualified }); router.push(buildLogBetUrl(row)) }} />
        </div>
      </div>
    )
  }

  function renderMobileSection(
    sorted: ComputedRow[],
    renderCard: (row: ComputedRow) => React.ReactNode,
    emptyMessage: string,
  ) {
    if (isLoading) return <SkeletonCards />
    if (sorted.length === 0) {
      return <p className="py-8 text-center text-sm text-gray-500">{emptyMessage}</p>
    }
    const qualified = sorted.filter(r => r.qualified)
    const unqualified = sorted.filter(r => !r.qualified)
    return (
      <div className="space-y-3">
        {qualified.map(row => renderCard(row))}
        {qualified.length > 0 && unqualified.length > 0 && <MobileNotRecommendedDivider />}
        {unqualified.map(row => renderCard(row))}
      </div>
    )
  }

  return (
    <AuthGuard>
    <div className="min-h-screen bg-[#0a0a0a] font-sans text-white">
      <Nav authenticated activeLink="ev-tracker" userEmail={email} />

      <main className="mx-auto max-w-6xl px-4 py-8">
        {/* ----------------------------------------------------------------
            Page header + controls
        ---------------------------------------------------------------- */}
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">Expected Value Tracker</h1>
            <p className="mt-0.5 text-sm text-gray-500">
              All markets · Kelly-sized stakes · Full model transparency
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Date picker */}
            <Popover open={calOpen} onOpenChange={setCalOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline"
                  className="h-9 w-[156px] justify-start gap-2 border-[#262626] bg-[#141414] text-left text-sm font-normal text-white hover:bg-[#1a1a1a]">
                  <CalendarIcon className="h-4 w-4 text-gray-500" />
                  {format(selectedDate, "MMM d, yyyy")}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto border-[#262626] bg-[#141414] p-0" align="end">
                <Calendar mode="single" selected={selectedDate}
                  onSelect={(d) => { if (d) { setSelectedDate(d); setCalOpen(false) } }}
                  toDate={new Date()}
                  initialFocus />
              </PopoverContent>
            </Popover>

            {/* Bankroll — label inside border for consistent alignment */}
            <div className="flex h-9 items-center rounded-md border border-[#262626] bg-[#141414] px-2.5">
              <span className="mr-1.5 text-xs text-gray-500">Bankroll</span>
              <span className="text-sm text-gray-500">$</span>
              <input
                type="number" min={0} step={100} value={bankroll}
                onChange={(e) => setBankroll(Number(e.target.value))}
                className="w-20 bg-transparent pl-0.5 text-sm text-white outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
              />
            </div>

            {/* Max Kelly cap — label inside border */}
            <div className="flex h-9 items-center rounded-md border border-[#262626] bg-[#141414] px-2.5">
              <TooltipProvider delayDuration={150}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="mr-1.5 cursor-help text-xs text-gray-500 border-b border-dotted border-gray-700">Kelly cap</span>
                  </TooltipTrigger>
                  <TooltipContent side="top" className="max-w-[200px] text-center text-xs text-white border-[#262626] bg-[#1a1a1a]">
                    Maximum stake as % of bankroll per bet. Kelly stakes above this are capped.
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
              <input
                type="number" min={1} max={25} step={1} value={maxKelly}
                onChange={(e) => setMaxKelly(Math.max(1, Math.min(25, Number(e.target.value))))}
                className="w-8 bg-transparent text-sm text-white outline-none text-center [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
              />
              <span className="text-sm text-gray-500">%</span>
            </div>

            {/* Book (Bovada only — DraftKings/FanDuel require separate data modeling) */}
            <div className="flex h-9 items-center rounded-md border border-[#262626] bg-[#141414] px-2.5">
              <span className="mr-1.5 text-xs text-gray-500">Book</span>
              <span className="text-sm text-gray-400">Bovada</span>
            </div>
          </div>
        </div>

        {/* ----------------------------------------------------------------
            Summary bar
        ---------------------------------------------------------------- */}
        <div className="mb-6 rounded-xl border border-[#262626] bg-[#141414] px-5 py-3.5">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
            <span>
              <span className="font-semibold text-[#10b981]">{qualifiedCount}</span>
              <span className="text-gray-500"> qualified markets</span>
            </span>
            <span className="text-gray-700">·</span>
            <span>
              <span className="font-semibold text-gray-300">{totalCount}</span>
              <span className="text-gray-500"> total markets</span>
            </span>
            <span className="text-gray-700">·</span>
            <span>
              <TooltipProvider delayDuration={150}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="cursor-help text-gray-500 border-b border-dotted border-gray-700">Est. daily EV</span>
                </TooltipTrigger>
                <TooltipContent side="top" className="max-w-[260px] text-center text-xs text-white border-[#262626] bg-[#1a1a1a]">
                  Sum of (EV × Stake) across all qualified bets. If the model is accurate over many bets, this is the expected dollar gain today at your bankroll size.
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <span className="text-gray-700">: </span>
              <span className={cn("font-semibold", estDailyEV >= 0 ? "text-[#10b981]" : "text-[#ef4444]")}>
                {estDailyEV >= 0 ? "+" : ""}${estDailyEV.toFixed(2)}
              </span>
            </span>
          </div>
        </div>

        {/* ----------------------------------------------------------------
            Preliminary banner
        ---------------------------------------------------------------- */}
        {data?.is_preliminary && (
          <div className="mb-6 flex items-start gap-2.5 rounded-lg border border-amber-800 bg-amber-950 px-4 py-3 text-sm text-amber-300">
            <span className="mt-0.5 shrink-0 font-bold">⚠</span>
            <span>
              <span className="font-semibold">Preliminary predictions</span> — lineups not yet confirmed.
              These picks are based on probable pitchers only. Do not bet until confirmed lineups are posted (~90 min before first pitch).
            </span>
          </div>
        )}

        {/* ----------------------------------------------------------------
            Moneyline
        ---------------------------------------------------------------- */}
        <div className="mb-8">
          <div className="mb-3 flex items-center gap-3">
            <h2 className="text-base font-semibold text-white">Moneyline</h2>
            <Badge variant="outline" className="border-blue-800 bg-blue-950 text-blue-400 text-[10px] font-medium px-2 py-0">
              {sortedH2h.length}
            </Badge>
          </div>

          {/* Desktop table */}
          <div className="hidden md:block rounded-xl border border-[#262626] bg-[#141414]">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader className="sticky top-0 z-20 bg-[#141414]">
                  <TableRow className="border-b border-[#262626] hover:bg-transparent">
                    <TableHead className={thCls} onClick={() => handleH2hSort("game")}>Game <SortIcon col="game" sortKey={h2hSort} sortDir={h2hDir} /></TableHead>
                    <TableHead className={thCls} onClick={() => handleH2hSort("market")}>Pick <SortIcon col="market" sortKey={h2hSort} sortDir={h2hDir} /></TableHead>
                    <TableHead className={cn(thCls, "text-right")} onClick={() => handleH2hSort("modelProb")}>
                      <ColHeaderTip label="Model%" tip="Model's win probability for the picked team, shown as ±% from 50%." /> <SortIcon col="modelProb" sortKey={h2hSort} sortDir={h2hDir} />
                    </TableHead>
                    <TableHead className={cn(thCls, "text-right")} onClick={() => handleH2hSort("bovadaProb")}>
                      <ColHeaderTip label="Book%" tip="Bovada's de-vigged (fair) implied probability for the picked team, shown as ±% from 50%." /> <SortIcon col="bovadaProb" sortKey={h2hSort} sortDir={h2hDir} />
                    </TableHead>
                    <TableHead className={cn(thNoCls, "text-right")}>Line</TableHead>
                    <TableHead className={cn(thCls, "text-right")} onClick={() => handleH2hSort("edge")}>
                      <ColHeaderTip label="Edge" tip="Model probability minus book implied probability for the picked side. Larger = stronger model-vs-market disagreement." /> <SortIcon col="edge" sortKey={h2hSort} sortDir={h2hDir} />
                    </TableHead>
                    <TableHead className={cn(thCls, "text-right")} onClick={() => handleH2hSort("ev")}>
                      <ColHeaderTip label="EV" tip="Expected value per dollar bet. +5% means you expect to gain $0.05 per $1 wagered on average if the model is accurate over many bets." /> <SortIcon col="ev" sortKey={h2hSort} sortDir={h2hDir} />
                    </TableHead>
                    <TableHead className={cn(thCls, "text-right hidden xl:table-cell")} onClick={() => handleH2hSort("rawKelly")}>
                      <ColHeaderTip label="Kelly%" tip="Full Kelly criterion — the mathematically optimal stake as % of bankroll. Can be volatile; higher values carry more risk." /> <SortIcon col="rawKelly" sortKey={h2hSort} sortDir={h2hDir} />
                    </TableHead>
                    <TableHead className={cn(thCls, "text-right")} onClick={() => handleH2hSort("cappedKelly")}>
                      <ColHeaderTip label={`Capped%`} tip={`Kelly% capped at your max (${maxKelly}%). This is the recommended stake size — it limits downside if the model is temporarily wrong.`} /> <SortIcon col="cappedKelly" sortKey={h2hSort} sortDir={h2hDir} />
                    </TableHead>
                    <TableHead className={cn(thCls, "text-right")} onClick={() => handleH2hSort("stake")}>Stake <SortIcon col="stake" sortKey={h2hSort} sortDir={h2hDir} /></TableHead>
                    <TableHead className={cn(thNoCls, "text-center")}>Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody className="[&>tr:last-child>td]:border-b-0">
                  {renderTableBody(sortedH2h, renderH2hRow, 11, "No moneyline markets for this date", 11)}
                </TableBody>
              </Table>
            </div>
          </div>

          {/* Mobile cards */}
          <div className="md:hidden">
            <MobileSortPills
              sortKey={h2hSort} sortDir={h2hDir} onSort={handleH2hSort}
              options={[
                { key: "game", label: "Time" },
                { key: "edge", label: "Edge" },
                { key: "ev", label: "EV" },
                { key: "stake", label: "Stake" },
              ]}
            />
            {renderMobileSection(sortedH2h, renderH2hCard, "No moneyline markets for this date")}
          </div>
        </div>

        {/* ----------------------------------------------------------------
            Total Runs
        ---------------------------------------------------------------- */}
        <div>
          <div className="mb-3 flex items-center gap-3">
            <h2 className="text-base font-semibold text-white">Total Runs</h2>
            <Badge variant="outline" className="border-teal-800 bg-teal-950 text-teal-400 text-[10px] font-medium px-2 py-0">
              {sortedTotals.length}
            </Badge>
          </div>

          {/* Desktop table */}
          <div className="hidden md:block rounded-xl border border-[#262626] bg-[#141414]">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader className="sticky top-0 z-20 bg-[#141414]">
                  <TableRow className="border-b border-[#262626] hover:bg-transparent">
                    <TableHead className={thCls} onClick={() => handleTotalsSort("game")}>Game <SortIcon col="game" sortKey={totalsSort} sortDir={totalsDir} /></TableHead>
                    <TableHead className={thCls} onClick={() => handleTotalsSort("market")}>Pick <SortIcon col="market" sortKey={totalsSort} sortDir={totalsDir} /></TableHead>
                    <TableHead className={cn(thCls, "text-right")} onClick={() => handleTotalsSort("predRuns")}>
                      <ColHeaderTip label="Proj. Runs" tip="Model's predicted total combined runs for the game. Compare to the book line in the Pick badge." /> <SortIcon col="predRuns" sortKey={totalsSort} sortDir={totalsDir} />
                    </TableHead>
                    <TableHead className={cn(thCls, "text-right")} onClick={() => handleTotalsSort("edge")}>
                      <ColHeaderTip label="Edge" tip="Model probability minus book implied probability for the picked side (Over or Under). Larger = stronger disagreement." /> <SortIcon col="edge" sortKey={totalsSort} sortDir={totalsDir} />
                    </TableHead>
                    <TableHead className={cn(thCls, "text-right")} onClick={() => handleTotalsSort("ev")}>
                      <ColHeaderTip label="EV" tip="Expected value per dollar bet. +5% means you expect to gain $0.05 per $1 wagered on average if the model is accurate over many bets." /> <SortIcon col="ev" sortKey={totalsSort} sortDir={totalsDir} />
                    </TableHead>
                    <TableHead className={cn(thCls, "text-right hidden xl:table-cell")} onClick={() => handleTotalsSort("rawKelly")}>
                      <ColHeaderTip label="Kelly%" tip="Full Kelly criterion — the mathematically optimal stake as % of bankroll. Can be volatile; higher values carry more risk." /> <SortIcon col="rawKelly" sortKey={totalsSort} sortDir={totalsDir} />
                    </TableHead>
                    <TableHead className={cn(thCls, "text-right")} onClick={() => handleTotalsSort("cappedKelly")}>
                      <ColHeaderTip label="Capped%" tip={`Kelly% capped at your max (${maxKelly}%). This is the recommended stake size — it limits downside if the model is temporarily wrong.`} /> <SortIcon col="cappedKelly" sortKey={totalsSort} sortDir={totalsDir} />
                    </TableHead>
                    <TableHead className={cn(thCls, "text-right")} onClick={() => handleTotalsSort("stake")}>Stake <SortIcon col="stake" sortKey={totalsSort} sortDir={totalsDir} /></TableHead>
                    <TableHead className={cn(thNoCls, "text-center")}>Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody className="[&>tr:last-child>td]:border-b-0">
                  {renderTableBody(sortedTotals, renderTotalsRow, 9, "No total runs markets for this date", 9)}
                </TableBody>
              </Table>
            </div>
          </div>

          {/* Mobile cards */}
          <div className="md:hidden">
            <MobileSortPills
              sortKey={totalsSort} sortDir={totalsDir} onSort={handleTotalsSort}
              options={[
                { key: "game", label: "Time" },
                { key: "predRuns", label: "Proj. Runs" },
                { key: "edge", label: "Edge" },
                { key: "ev", label: "EV" },
                { key: "stake", label: "Stake" },
              ]}
            />
            {renderMobileSection(sortedTotals, renderTotalsCard, "No total runs markets for this date")}
          </div>
        </div>

        {/* ----------------------------------------------------------------
            E9.11 — Line Shopping: best price across books for model-positive plays
        ---------------------------------------------------------------- */}
        <div className="mt-8">
          <Collapsible defaultOpen={true}>
            <CollapsibleTrigger asChild>
              <button className="w-full flex items-center justify-between mb-3 group">
                <div className="flex items-center gap-3">
                  <h2 className="text-base font-semibold text-white">Line Shopping</h2>
                  <Badge variant="outline" className="border-[#a78bfa]/40 bg-[#a78bfa]/10 text-[#a78bfa] text-[10px] font-medium px-2 py-0">
                    {lsData?.plays?.length ?? 0}
                  </Badge>
                  <TooltipProvider delayDuration={150}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="cursor-help text-[10px] font-medium uppercase tracking-wide text-gray-600 border-b border-dotted border-gray-700">
                          Model-relative
                        </span>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="max-w-[280px] text-center text-xs text-white border-[#262626] bg-[#1a1a1a]">
                        "+EV" here means the model estimates a higher probability than the book&apos;s de-vigged price. Our models have no demonstrated market edge (best_alpha=0). This is a line-shopping transparency tool — if you&apos;re going to bet this side, here&apos;s the best number and where to find it. Not a bet recommendation.
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>
                <ChevronDown className="h-4 w-4 text-gray-500 transition-transform duration-200 group-data-[state=open]:rotate-180" />
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              {/* Desktop table */}
              <div className="hidden md:block rounded-xl border border-[#262626] bg-[#141414]">
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader className="sticky top-0 z-20 bg-[#141414]">
                      <TableRow className="border-b border-[#262626] hover:bg-transparent">
                        <TableHead className={thNoCls}>Game</TableHead>
                        <TableHead className={thNoCls}>Pick</TableHead>
                        <TableHead className={cn(thNoCls, "text-right")}>Best Book</TableHead>
                        <TableHead className={cn(thNoCls, "text-right")}>
                          <ColHeaderTip label="Best Price" tip="Best available American odds for this side across all tracked US books (Pinnacle excluded — not US-bettable)." />
                        </TableHead>
                        <TableHead className={cn(thNoCls, "text-right")}>
                          <ColHeaderTip label="Mkt %" tip="The best book's de-vigged implied probability for this side." />
                        </TableHead>
                        <TableHead className={cn(thNoCls, "text-right")}>
                          <ColHeaderTip label="Model %" tip="The model's estimated probability for this side (model-relative; no demonstrated market edge)." />
                        </TableHead>
                        <TableHead className={cn(thNoCls, "text-right")}>
                          <ColHeaderTip label="Edge" tip="Model probability minus best book de-vigged probability. Always positive in this view." />
                        </TableHead>
                        <TableHead className={cn(thNoCls, "text-right")}>
                          <ColHeaderTip label="Breakeven" tip="American odds at which the model's EV = 0 (E9.1 model breakeven). If the best price is better than this, the model calls it +EV." />
                        </TableHead>
                        <TableHead className={cn(thNoCls, "text-right")}>
                          <ColHeaderTip label="Pinnacle" tip="Pinnacle's de-vigged fair-value probability — the sharpest, lowest-vig reference. More honest than our model as a market anchor." />
                        </TableHead>
                        <TableHead className={cn(thNoCls, "text-center")}>Detail</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody className="[&>tr:last-child>td]:border-b-0">
                      {lsLoading ? (
                        <SkeletonRows cols={10} />
                      ) : !lsData?.plays?.length ? (
                        <TableRow>
                          <TableCell colSpan={10} className="py-12 text-center text-sm text-gray-500">
                            No model-positive plays vs. best book price for this date
                          </TableCell>
                        </TableRow>
                      ) : (lsData.plays).map((play) => {
                        const homeTeam = normalizeTeam(play.home_team ?? "Home")
                        const awayTeam = normalizeTeam(play.away_team ?? "Away")
                        const game = `${awayTeam} @ ${homeTeam}`
                        const isTotal = play.market_type === "totals"
                        const sideLabel = isTotal
                          ? (play.side === "over" ? "Over" : "Under")
                          : (play.side === "home" ? homeTeam : awayTeam)
                        const marketLabel = isTotal ? `${sideLabel} ML` : `${sideLabel} ML`
                        const gameTime = formatGameTime(play.game_start_utc)
                        const gameDate = play.game_date ? format(new Date(play.game_date + "T12:00:00"), "MMM d") : "—"
                        const timeLabel = gameTime ? `${gameDate} · ${gameTime}` : gameDate
                        return (
                          <TableRow
                            key={`ls-${play.game_pk}-${play.market_type}-${play.side}`}
                            onClick={() => router.push(`/picks/${play.game_pk}`)}
                            className="border-b border-[#262626] transition-colors cursor-pointer hover:bg-[#a78bfa08]"
                          >
                            <TableCell className="py-3 pl-4 pr-3">
                              <p className="text-sm font-medium text-white">{game}</p>
                              <p className="text-xs text-gray-500">{timeLabel}</p>
                            </TableCell>
                            <TableCell className="px-3 py-3">
                              <MarketBadge type={play.market_type} label={`${sideLabel}${isTotal ? "" : " ML"}`} />
                            </TableCell>
                            <TableCell className="px-3 py-3 text-right">
                              <span className="text-sm font-semibold text-[#a78bfa]">
                                {LS_BOOK_LABELS[play.best_book_key] ?? play.best_book_name}
                              </span>
                            </TableCell>
                            <TableCell className="px-3 py-3 text-right text-sm font-bold text-[#10b981]">
                              {fmtAmerican(play.best_american)}
                            </TableCell>
                            <TableCell className="px-3 py-3 text-right text-sm text-gray-400">
                              {pctRaw(play.best_devigged_prob)}
                            </TableCell>
                            <TableCell className="px-3 py-3 text-right text-sm font-medium text-[#10b981]">
                              {pctRaw(play.model_prob)}
                            </TableCell>
                            <TableCell className="px-3 py-3 text-right text-sm font-semibold text-[#10b981]">
                              {fmtEdge(play.edge)}
                            </TableCell>
                            <TableCell className="px-3 py-3 text-right text-sm text-gray-500">
                              {play.breakeven_american != null ? fmtAmerican(play.breakeven_american) : "—"}
                            </TableCell>
                            <TableCell className="px-3 py-3 text-right text-sm text-[#a78bfa]">
                              {play.pinnacle_devigged_prob != null ? pctRaw(play.pinnacle_devigged_prob) : "—"}
                            </TableCell>
                            <TableCell className="px-3 py-3 text-center">
                              <Link
                                href={`/picks/${play.game_pk}`}
                                onClick={(e) => e.stopPropagation()}
                                className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 transition-colors"
                              >
                                <ExternalLink className="h-3 w-3" />
                              </Link>
                            </TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                </div>
              </div>

              {/* Mobile cards */}
              <div className="md:hidden space-y-3">
                {lsLoading ? (
                  <SkeletonCards />
                ) : !lsData?.plays?.length ? (
                  <p className="py-8 text-center text-sm text-gray-500">No model-positive plays vs. best book price for this date</p>
                ) : lsData.plays.map((play) => {
                  const homeTeam = normalizeTeam(play.home_team ?? "Home")
                  const awayTeam = normalizeTeam(play.away_team ?? "Away")
                  const isTotal = play.market_type === "totals"
                  const sideLabel = isTotal
                    ? (play.side === "over" ? "Over" : "Under")
                    : (play.side === "home" ? homeTeam : awayTeam)
                  const gameTime = formatGameTime(play.game_start_utc)
                  const gameDate = play.game_date ? format(new Date(play.game_date + "T12:00:00"), "MMM d") : "—"
                  const timeLabel = gameTime ? `${gameDate} · ${gameTime}` : gameDate
                  return (
                    <div
                      key={`ls-card-${play.game_pk}-${play.market_type}-${play.side}`}
                      onClick={() => router.push(`/picks/${play.game_pk}`)}
                      className="rounded-xl border border-[#262626] bg-[#141414] p-4 transition-colors cursor-pointer active:bg-[#a78bfa08]"
                    >
                      <div className="mb-2 flex items-start justify-between gap-2">
                        <span className="text-sm font-medium text-white">{`${awayTeam} @ ${homeTeam}`}</span>
                        <span className="shrink-0 text-xs text-gray-500">{timeLabel}</span>
                      </div>
                      <div className="mb-3">
                        <MarketBadge type={play.market_type} label={`${sideLabel}${isTotal ? "" : " ML"}`} />
                      </div>
                      <div className="grid grid-cols-2 gap-x-6 gap-y-2 mb-3">
                        <div>
                          <p className="text-[10px] font-medium uppercase tracking-wide text-gray-600">Best Book</p>
                          <p className="mt-0.5 text-sm font-semibold text-[#a78bfa]">
                            {LS_BOOK_LABELS[play.best_book_key] ?? play.best_book_name}
                          </p>
                        </div>
                        <div>
                          <p className="text-[10px] font-medium uppercase tracking-wide text-gray-600">Best Price</p>
                          <p className="mt-0.5 text-sm font-bold text-[#10b981]">{fmtAmerican(play.best_american)}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-medium uppercase tracking-wide text-gray-600">Edge</p>
                          <p className="mt-0.5 text-sm font-semibold text-[#10b981]">{fmtEdge(play.edge)}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-medium uppercase tracking-wide text-gray-600">Breakeven</p>
                          <p className="mt-0.5 text-sm text-gray-400">
                            {play.breakeven_american != null ? fmtAmerican(play.breakeven_american) : "—"}
                          </p>
                        </div>
                        <div>
                          <p className="text-[10px] font-medium uppercase tracking-wide text-gray-600">Pinnacle</p>
                          <p className="mt-0.5 text-sm text-[#a78bfa]">
                            {play.pinnacle_devigged_prob != null ? pctRaw(play.pinnacle_devigged_prob) : "—"}
                          </p>
                        </div>
                        <div>
                          <p className="text-[10px] font-medium uppercase tracking-wide text-gray-600">Model %</p>
                          <p className="mt-0.5 text-sm font-medium text-[#10b981]">{pctRaw(play.model_prob)}</p>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>

              <p className="mt-3 text-xs text-gray-600">
                Line Shopping shows plays where the model is above the best US book&apos;s de-vigged price.
                Sorted by edge (largest first). Pinnacle is the sharpest fair-value anchor — not US-bettable.
                <span className="ml-1 text-gray-700">best_alpha=0 — no demonstrated edge over the market.</span>
              </p>
            </CollapsibleContent>
          </Collapsible>
        </div>

        {/* Footer */}
        <p className="mt-4 text-center text-xs text-gray-600">
          Kelly stakes capped at {maxKelly}% per bet. EV and Kelly calculated from model vs. Bovada implied probabilities.
          HC = High Conviction (strong multi-signal agreement). Not financial advice.
        </p>
      </main>
    </div>
    </AuthGuard>
  )
}
