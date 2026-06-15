"use client"

import React, { Suspense, useEffect, useState } from "react"
import Link from "next/link"
import posthog from "posthog-js"
import { useRouter, useSearchParams } from "next/navigation"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { AuthGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { Nav } from "@/components/nav"
import { format } from "date-fns"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog"
import { CalendarIcon, CheckCircle, Pencil, Trash2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { apiFetch } from "@/lib/api"
import { normalizeTeam, normalizeMatchup } from "@/lib/teams"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type BetStatus = "Won" | "Lost" | "Push" | "Open" | "Void"

interface GameOption {
  game_pk: number
  label: string      // "NYY @ BOS"
  score_date: string // "2026-06-12"
}

interface ApiBet {
  bet_id: string
  game_pk: number
  score_date: string
  matchup: string | null
  market: string
  bookmaker: string | null
  american_odds: number
  stake: number
  outcome: string | null
  profit_loss: number | null
  ev: number | null
  model_prob: number | null
  total_line: number | null
  notes: string | null
  placed_at: string
}

interface BetsResponse {
  bets: ApiBet[]
  total: number
}

interface EVPick {
  game_pk: number
  game_date: string | null
  game_start_utc: string | null
  market_type: string  // "h2h" | "totals"
  model_prob: number | null
  bovada_devig_prob: number | null
  home_team: string | null
  away_team: string | null
}

interface EVPicksResponse {
  picks: EVPick[]
  total: number
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
// Values must match the API validator: {"h2h home","h2h away","over","under"}
const MARKET_OPTIONS = [
  { label: "Home ML", value: "h2h home" },
  { label: "Away ML", value: "h2h away" },
  { label: "Over",    value: "over"     },
  { label: "Under",   value: "under"    },
]

const BOOKMAKER_OPTIONS = ["Bovada", "DraftKings", "FanDuel", "BetMGM", "Pinnacle", "Other"]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function marketDisplay(m: string): string {
  const map: Record<string, string> = {
    "h2h home": "Home ML",
    "h2h away": "Away ML",
    "over": "Over",
    "under": "Under",
  }
  return map[m] ?? m
}

function outcomeToStatus(outcome: string | null): BetStatus {
  if (outcome === "win")  return "Won"
  if (outcome === "loss") return "Lost"
  if (outcome === "push") return "Push"
  if (outcome === "void") return "Void"
  return "Open"
}

// Map EV tracker's `side` param to API market value
function sideToMarketValue(side: string): string {
  if (side === "Home")  return "h2h home"
  if (side === "Away")  return "h2h away"
  if (side === "Over")  return "over"
  if (side === "Under") return "under"
  return ""
}

// Return model + bovada probs from the perspective of the picked side
function getLiveProbData(
  picks: EVPick[], gamePk: number, market: string,
): { modelProb: number; bovadaProb: number } | null {
  const marketType = market.startsWith("h2h") ? "h2h" : "totals"
  const pick = picks.find(p => p.game_pk === gamePk && p.market_type === marketType)
  if (!pick || pick.model_prob == null || pick.bovada_devig_prob == null) return null
  let { model_prob: mp, bovada_devig_prob: bp } = pick
  if (market === "h2h away" || market === "under") { mp = 1 - mp; bp = 1 - bp }
  return { modelProb: mp, bovadaProb: bp }
}

// For Bovada auto-fill: derive American odds from bovada_devig_prob
// h2h away / under → flip probability
function getAutoOdds(picks: EVPick[], gamePk: number, market: string): string {
  const marketType = market.startsWith("h2h") ? "h2h" : "totals"
  const pick = picks.find(p => p.game_pk === gamePk && p.market_type === marketType)
  if (!pick || pick.bovada_devig_prob == null) return ""
  let prob = pick.bovada_devig_prob
  if (market === "h2h away" || market === "under") prob = 1 - prob
  return String(probToAmerican(prob))
}

function probToAmerican(prob: number): number {
  if (prob >= 0.5) return Math.round(-(prob / (1 - prob)) * 100)
  return Math.round(((1 - prob) / prob) * 100)
}

function fmtPnl(val: number | null): string {
  if (val === null) return "—"
  const sign = val >= 0 ? "+" : ""
  return `${sign}$${Math.abs(val).toFixed(2)}`
}

function fmtOdds(odds: number): string {
  return odds > 0 ? `+${odds}` : String(odds)
}

function calcProfitLoss(outcome: string, stake: number, odds: number): number {
  if (outcome === "loss") return -stake
  if (outcome === "push") return 0
  // win
  return odds > 0 ? (odds / 100) * stake : (100 / Math.abs(odds)) * stake
}

function fmtEv(ev: number | null): { text: string; cls: string } {
  if (ev === null) return { text: "—", cls: "text-gray-600" }
  const sign = ev >= 0 ? "+" : ""
  return {
    text: `${sign}${(ev * 100).toFixed(1)}%`,
    cls: ev >= 0 ? "text-[#10b981]" : "text-[#ef4444]",
  }
}

// ---------------------------------------------------------------------------
// Edit Bet modal
// ---------------------------------------------------------------------------
const OUTCOME_OPTIONS = [
  { label: "Pending",            value: "pending" },
  { label: "Won",                value: "win" },
  { label: "Lost",               value: "loss" },
  { label: "Push",               value: "push" },
  { label: "Void (postponed)",   value: "void" },
]

function EditBetModal({
  bet,
  onClose,
  onSave,
  isSaving,
}: {
  bet: ApiBet
  onClose: () => void
  onSave: (patch: object) => void
  isSaving: boolean
}) {
  const [market, setMarket]       = useState(bet.market)
  const [bookmaker, setBookmaker] = useState(bet.bookmaker ?? "Bovada")
  const [odds, setOdds]           = useState(String(bet.american_odds))
  const [stake, setStake]         = useState(String(bet.stake))
  const [totalLine, setTotalLine] = useState(bet.total_line != null ? String(bet.total_line) : "")
  const [notes, setNotes]         = useState(bet.notes ?? "")
  const [outcome, setOutcome]     = useState(bet.outcome ?? "pending")

  const isTotal = market === "over" || market === "under"

  function handleSave() {
    const patch: Record<string, unknown> = {
      market,
      bookmaker,
      american_odds: Number(odds),
      stake: Number(stake),
      ...(isTotal && totalLine ? { total_line: Number(totalLine) } : {}),
      ...(notes ? { notes } : {}),
    }
    if (outcome && outcome !== "pending") {
      patch.outcome = outcome
      patch.profit_loss = calcProfitLoss(outcome, Number(stake), Number(odds))
    } else {
      patch.outcome = null
      patch.profit_loss = null
    }
    onSave(patch)
  }

  return (
    <Dialog open onOpenChange={open => { if (!open) onClose() }}>
      <DialogContent className="border-[#262626] bg-[#141414] text-white sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-white">Edit Bet</DialogTitle>
          <p className="text-xs text-gray-500">{bet.matchup ?? `Game ${bet.game_pk}`} · {bet.score_date}</p>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-4 py-2">
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-gray-400">Market</Label>
            <Select value={market} onValueChange={setMarket}>
              <SelectTrigger className="border-[#262626] bg-[#0a0a0a] text-sm text-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="border-[#262626] bg-[#141414]">
                {MARKET_OPTIONS.map(m => (
                  <SelectItem key={m.value} value={m.value} className="text-sm text-white focus:bg-[#1e1e1e] focus:text-white">{m.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-gray-400">Bookmaker</Label>
            <Select value={bookmaker} onValueChange={setBookmaker}>
              <SelectTrigger className="border-[#262626] bg-[#0a0a0a] text-sm text-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="border-[#262626] bg-[#141414]">
                {BOOKMAKER_OPTIONS.map(b => (
                  <SelectItem key={b} value={b} className="text-sm text-white focus:bg-[#1e1e1e] focus:text-white">{b}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-gray-400">Odds (American)</Label>
            <Input type="number" value={odds} onChange={e => setOdds(e.target.value)}
              className="border-[#262626] bg-[#0a0a0a] text-sm text-white" />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-gray-400">Stake ($)</Label>
            <Input type="number" step="any" min={0.01} value={stake} onChange={e => setStake(e.target.value)}
              className="border-[#262626] bg-[#0a0a0a] text-sm text-white" />
          </div>

          {isTotal && (
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs text-gray-400">Total Line</Label>
              <Input type="number" value={totalLine} onChange={e => setTotalLine(e.target.value)}
                placeholder="8.5" className="border-[#262626] bg-[#0a0a0a] text-sm text-white" />
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-gray-400">Outcome</Label>
            <Select value={outcome} onValueChange={setOutcome}>
              <SelectTrigger className="border-[#262626] bg-[#0a0a0a] text-sm text-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="border-[#262626] bg-[#141414]">
                {OUTCOME_OPTIONS.map(o => (
                  <SelectItem key={o.value} value={o.value} className="text-sm text-white focus:bg-[#1e1e1e] focus:text-white">{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="col-span-2 flex flex-col gap-1.5">
            <Label className="text-xs text-gray-400">Notes (optional)</Label>
            <Input value={notes} onChange={e => setNotes(e.target.value)}
              placeholder="Any context about this bet..."
              className="border-[#262626] bg-[#0a0a0a] text-sm text-white placeholder:text-gray-600" />
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="ghost" onClick={onClose}
            className="text-gray-400 hover:text-white hover:bg-[#1a1a1a]">Cancel</Button>
          <Button onClick={handleSave} disabled={!odds || !stake || isSaving}
            className="bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]">
            {isSaving ? "Saving…" : "Save Changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------
function StatusBadge({ status }: { status: BetStatus }) {
  if (status === "Won")  return <Badge className="bg-[#10b981] text-[#0a0a0a] text-xs font-semibold">Won</Badge>
  if (status === "Lost") return <Badge className="bg-[#ef4444] text-white text-xs font-semibold">Lost</Badge>
  if (status === "Push") return <Badge variant="outline" className="border-[#f59e0b] text-[#f59e0b] text-xs">Push</Badge>
  if (status === "Void") return <Badge variant="outline" className="border-[#6366f1] text-[#6366f1] text-xs">Void</Badge>
  return <Badge variant="outline" className="border-[#404040] text-gray-400 text-xs">Open</Badge>
}

// ---------------------------------------------------------------------------
// Summary tiles — computed from live API bets
// ---------------------------------------------------------------------------
function SummaryTiles({ bets }: { bets: ApiBet[] }) {
  const settled    = bets.filter(b => b.outcome !== null && b.outcome !== "void")
  const won        = bets.filter(b => b.outcome === "win")
  const netPnl     = settled.reduce((acc, b) => acc + (b.profit_loss ?? 0), 0)
  const totalStaked = settled.reduce((acc, b) => acc + b.stake, 0)
  const roi        = totalStaked > 0 ? (netPnl / totalStaked) * 100 : 0
  const winRate    = settled.length > 0 ? (won.length / settled.length) * 100 : 0

  const tiles = [
    { label: "Net P&L",  value: fmtPnl(netPnl),                             positive: netPnl >= 0 },
    { label: "ROI",      value: `${roi >= 0 ? "+" : ""}${roi.toFixed(1)}%`, positive: roi >= 0 },
    { label: "Win Rate", value: `${winRate.toFixed(1)}%`,                    positive: winRate >= 50 },
  ]

  return (
    <div className="grid grid-cols-3 gap-4 mb-6">
      {tiles.map(t => (
        <div key={t.label} className="rounded-lg border border-[#262626] bg-[#141414] px-5 py-4">
          <p className="text-xs text-gray-500 mb-1">{t.label}</p>
          <p className={cn("text-xl font-bold", t.positive ? "text-[#10b981]" : "text-[#ef4444]")}>{t.value}</p>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Inner page — uses useSearchParams, must be inside Suspense
// ---------------------------------------------------------------------------
function BetLogInner() {
  const searchParams  = useSearchParams()
  const { accessToken, email } = useAuth()
  const qc            = useQueryClient()

  const qGamePk     = searchParams.get("game_pk")    ? Number(searchParams.get("game_pk"))    : null
  const qSide       = searchParams.get("side")       ?? ""
  const qGameDate   = searchParams.get("game_date")  ?? null

  // ── Form state (date must be declared before queries that depend on it) ──
  const [date, setDate]           = useState<Date>(() => {
    if (qGameDate) {
      const d = new Date(qGameDate + "T12:00:00")
      if (!isNaN(d.getTime())) return d
    }
    return new Date()
  })
  const [calOpen, setCalOpen]     = useState(false)

  const selectedDateStr = format(date, "yyyy-MM-dd")

  // ── Data fetching ────────────────────────────────────────────────────────
  // EV data for selected date — drives game dropdown AND Bovada odds auto-fill
  // Always pass explicit date so the S3 cache key matches the EV tracker's key.
  const { data: evData } = useQuery<EVPicksResponse>({
    queryKey: ["picks-ev", selectedDateStr],
    queryFn:  () => apiFetch(`/picks/ev?date=${selectedDateStr}`, {}, accessToken),
    enabled:  !!accessToken,
    staleTime: 5 * 60 * 1000,
  })

  const { data: betsData, isLoading: betsLoading } = useQuery<BetsResponse>({
    queryKey: ["bets", accessToken],
    queryFn:  () => apiFetch("/bets", {}, accessToken),
    enabled:  !!accessToken,
  })

  // Deduplicated game options from EV data (works for any date)
  const gameOptions: GameOption[] = React.useMemo(() => {
    if (!evData?.picks) return []
    const seen = new Set<number>()
    return evData.picks
      .filter(p => { if (seen.has(p.game_pk)) return false; seen.add(p.game_pk); return true })
      .map(p => ({
        game_pk:    p.game_pk,
        label:      `${normalizeTeam(p.away_team ?? "Away")} @ ${normalizeTeam(p.home_team ?? "Home")}`,
        score_date: p.game_date ? String(p.game_date).slice(0, 10) : selectedDateStr,
      }))
  }, [evData, selectedDateStr])

  const prefillGame = qGamePk ? gameOptions.find(g => g.game_pk === qGamePk) : null

  // ── Remaining form state ─────────────────────────────────────────────────
  const [gamePk, setGamePk]       = useState<string>(qGamePk ? String(qGamePk) : "")
  const isPrefilled = !!qGamePk && !!prefillGame && gamePk === String(qGamePk)
  const [market, setMarket]       = useState<string>(qSide ? sideToMarketValue(qSide) : "")
  const [totalLine, setTotalLine] = useState<string>("")
  const [bookmaker, setBookmaker] = useState("Bovada")
  const [odds, setOdds]           = useState("")
  const [stake, setStake]         = useState("")
  const [notes, setNotes]         = useState("")
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [saveError, setSaveError]     = useState<string | null>(null)
  const [seasonFilter, setSeasonFilter] = useState<string>("all")
  const [deletingBetId, setDeletingBetId] = useState<string | null>(null)
  const [editingBet, setEditingBet]       = useState<ApiBet | null>(null)

  const isTotal = market === "over" || market === "under"

  // Live model/bovada probs from EV data for currently selected game+market
  const liveProbData = React.useMemo(() => {
    if (!gamePk || gamePk === "_none" || !market || !evData?.picks) return null
    return getLiveProbData(evData.picks, Number(gamePk), market)
  }, [gamePk, market, evData])

  // Auto-populate Bovada odds when game + market + bookmaker=Bovada are all set
  useEffect(() => {
    if (bookmaker !== "Bovada" || !gamePk || gamePk === "_none" || !market || !evData?.picks) return
    const auto = getAutoOdds(evData.picks, Number(gamePk), market)
    if (auto) setOdds(auto)
  }, [gamePk, market, bookmaker, evData])

  // ── Mutations ─────────────────────────────────────────────────────────────
  const saveMutation = useMutation({
    mutationFn: (body: object) =>
      apiFetch("/bets", { method: "POST", body: JSON.stringify(body) }, accessToken),
    onSuccess: (_data, body) => {
      const b = body as Record<string, unknown>
      posthog.capture("bet_logged", {
        market: b.market,
        bookmaker: b.bookmaker,
        american_odds: b.american_odds,
        stake: b.stake,
        ev: b.ev ?? null,
      })
      qc.invalidateQueries({ queryKey: ["bets"] })
      setGamePk("")
      setMarket("")
      setTotalLine("")
      setBookmaker("Bovada")
      setOdds("")
      setStake("")
      setNotes("")
      setSaveSuccess(true)
      setSaveError(null)
      setTimeout(() => setSaveSuccess(false), 2000)
    },
    onError: (err: Error) => {
      setSaveError(err.message)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (bet_id: string) =>
      apiFetch(`/bets/${bet_id}`, { method: "DELETE" }, accessToken),
    onSuccess: (_data, bet_id) => {
      posthog.capture("bet_deleted", { bet_id })
      qc.invalidateQueries({ queryKey: ["bets"] })
      setDeletingBetId(null)
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ bet_id, patch }: { bet_id: string; patch: object }) =>
      apiFetch(`/bets/${bet_id}`, { method: "PUT", body: JSON.stringify(patch) }, accessToken),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bets"] })
      setEditingBet(null)
    },
  })

  function handleSave() {
    const selectedGame = gameOptions.find(g => g.game_pk === Number(gamePk))
    if (!selectedGame || !market || !odds || !stake) return

    const mp = liveProbData?.modelProb ?? null
    const bp = liveProbData?.bovadaProb ?? null

    saveMutation.mutate({
      game_pk:      selectedGame.game_pk,
      score_date:   format(date, "yyyy-MM-dd"),
      matchup:      selectedGame.label,
      market,
      bookmaker,
      american_odds: Number(odds),
      stake:         Number(stake),
      ...(isTotal && totalLine ? { total_line: Number(totalLine) } : {}),
      ...(mp != null  ? { model_prob:  mp }  : {}),
      ...(bp != null  ? { market_prob: bp }  : {}),
      ...(mp != null && bp != null ? { ev: mp - bp } : {}),
      ...(notes ? { notes } : {}),
    })
  }

  const allBets = betsData?.bets ?? []

  // Derive available seasons from bet dates, newest first
  const availableSeasons = React.useMemo(() => {
    const years = new Set(allBets.map(b => b.score_date.slice(0, 4)))
    return Array.from(years).sort().reverse()
  }, [allBets])

  const bets = React.useMemo(() => {
    if (seasonFilter === "all") return allBets
    return allBets.filter(b => b.score_date.startsWith(seasonFilter))
  }, [allBets, seasonFilter])

  return (
    <AuthGuard>
    <div className="min-h-screen w-full overflow-x-hidden bg-[#0a0a0a]">
      <Nav authenticated activeLink="bet-log" userEmail={email} />

      <main className="mx-auto max-w-6xl px-4 py-8">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-white">Bet Log</h1>
          <p className="mt-1 text-sm text-gray-500">Log your bets and track performance using the model&apos;s edge estimates.</p>
        </div>

        <div className="flex flex-col gap-8">
          {/* ----------------------------------------------------------------
              Log a Bet form
          ---------------------------------------------------------------- */}
          <div className="rounded-lg border border-[#262626] bg-[#141414] p-6">
            <h2 className="mb-5 text-base font-semibold text-white">Log a Bet</h2>

            {isPrefilled && (
              <div className="mb-5 rounded-md border border-[#10b981]/30 bg-[#10b981]/10 px-3 py-2 text-xs text-[#10b981]">
                Pre-filled from EV Tracker &mdash; {prefillGame!.label},{" "}
                {MARKET_OPTIONS.find(m => m.value === market)?.label ?? market}
              </div>
            )}

            <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4 lg:grid-cols-7">
              {/* Date */}
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">Date</Label>
                <Popover open={calOpen} onOpenChange={setCalOpen}>
                  <PopoverTrigger asChild>
                    <Button variant="outline" className="w-full justify-start border-[#262626] bg-[#0a0a0a] text-sm text-white hover:bg-[#1a1a1a] hover:text-white">
                      <CalendarIcon className="mr-2 h-4 w-4 text-gray-500" />
                      {format(date, "MMM d, yyyy")}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto border-[#262626] bg-[#141414] p-0">
                    <Calendar mode="single" selected={date} onSelect={d => {
                      if (d) {
                        setDate(d)
                        setCalOpen(false)
                        setGamePk("")
                        setOdds("")
                      }
                    }} initialFocus />
                  </PopoverContent>
                </Popover>
              </div>

              {/* Game — populated from today's picks */}
              <div className="flex flex-col gap-1.5 col-span-1 sm:col-span-2">
                <Label className="text-xs text-gray-400">Game</Label>
                <Select value={gamePk} onValueChange={setGamePk}>
                  <SelectTrigger className="border-[#262626] bg-[#0a0a0a] text-sm text-white">
                    <SelectValue placeholder="Select game…" />
                  </SelectTrigger>
                  <SelectContent className="border-[#262626] bg-[#141414]">
                    {gameOptions.length === 0 ? (
                      <SelectItem value="_none" disabled className="text-sm text-gray-500">
                        No model data for {selectedDateStr}
                      </SelectItem>
                    ) : (
                      gameOptions.map(g => (
                        <SelectItem key={g.game_pk} value={String(g.game_pk)}
                          className="text-sm text-white focus:bg-[#1e1e1e] focus:text-white">
                          {g.label}
                        </SelectItem>
                      ))
                    )}
                  </SelectContent>
                </Select>
              </div>

              {/* Market */}
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">Market</Label>
                <Select value={market} onValueChange={setMarket}>
                  <SelectTrigger className="border-[#262626] bg-[#0a0a0a] text-sm text-white">
                    <SelectValue placeholder="Select market…" />
                  </SelectTrigger>
                  <SelectContent className="border-[#262626] bg-[#141414]">
                    {MARKET_OPTIONS.map(m => (
                      <SelectItem key={m.value} value={m.value}
                        className="text-sm text-white focus:bg-[#1e1e1e] focus:text-white">
                        {m.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Bookmaker */}
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">Bookmaker</Label>
                <Select value={bookmaker} onValueChange={setBookmaker}>
                  <SelectTrigger className="border-[#262626] bg-[#0a0a0a] text-sm text-white">
                    <SelectValue placeholder="Select bookmaker…" />
                  </SelectTrigger>
                  <SelectContent className="border-[#262626] bg-[#141414]">
                    {BOOKMAKER_OPTIONS.map(b => (
                      <SelectItem key={b} value={b}
                        className="text-sm text-white focus:bg-[#1e1e1e] focus:text-white">
                        {b}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Total Line — only shown for over/under markets */}
              {isTotal && (
                <div className="flex flex-col gap-1.5">
                  <Label className="text-xs text-gray-400">Total Line</Label>
                  <Input
                    type="number"
                    placeholder="8.5"
                    value={totalLine}
                    onChange={e => setTotalLine(e.target.value)}
                    className="border-[#262626] bg-[#0a0a0a] text-sm text-white placeholder:text-gray-600"
                  />
                </div>
              )}

              {/* Odds */}
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">Odds (American)</Label>
                <Input
                  type="number"
                  placeholder="-110"
                  value={odds}
                  onChange={e => setOdds(e.target.value)}
                  className="border-[#262626] bg-[#0a0a0a] text-sm text-white placeholder:text-gray-600"
                />
              </div>
            </div>

            {/* Second row: stake, notes, save */}
            <div className="mt-4 flex flex-wrap items-end gap-4">
              <div className="flex flex-col gap-1.5 w-32">
                <Label className="text-xs text-gray-400">Stake ($)</Label>
                <Input
                  type="number"
                  placeholder="50"
                  step="any"
                  min={0.01}
                  value={stake}
                  onChange={e => setStake(e.target.value)}
                  className="border-[#262626] bg-[#0a0a0a] text-sm text-white placeholder:text-gray-600"
                />
              </div>
              <div className="flex flex-col gap-1.5 flex-1 min-w-[180px]">
                <Label className="text-xs text-gray-400">Notes (optional)</Label>
                <Input
                  placeholder="Any context about this bet..."
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                  className="border-[#262626] bg-[#0a0a0a] text-sm text-white placeholder:text-gray-600"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Button
                  className="bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669] px-8"
                  onClick={handleSave}
                  disabled={!gamePk || gamePk === "_none" || !market || !odds || !stake || saveMutation.isPending}
                >
                  {saveMutation.isPending ? "Saving…" : "Save Bet"}
                </Button>
              </div>
              {saveSuccess && (
                <div className="flex items-center gap-2 text-xs text-[#10b981] pb-0.5">
                  <CheckCircle className="h-3.5 w-3.5" />
                  Bet logged successfully
                </div>
              )}
              {saveError && (
                <p className="text-xs text-[#ef4444] pb-0.5">{saveError}</p>
              )}
            </div>

            {liveProbData != null && (
              <p className="mt-3 text-xs text-gray-500">
                Model probability: <span className="text-gray-300">{(liveProbData.modelProb * 100).toFixed(1)}%</span>
                {" · "}Bovada: <span className="text-gray-300">{(liveProbData.bovadaProb * 100).toFixed(1)}%</span>
                {" · "}Edge:{" "}
                <span className={liveProbData.modelProb - liveProbData.bovadaProb >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}>
                  {liveProbData.modelProb - liveProbData.bovadaProb >= 0 ? "+" : ""}
                  {((liveProbData.modelProb - liveProbData.bovadaProb) * 100).toFixed(1)}%
                </span>
              </p>
            )}
          </div>

          {/* ----------------------------------------------------------------
              Summary tiles + bet history
          ---------------------------------------------------------------- */}
          <div className="flex flex-col gap-0 min-w-0">
            <SummaryTiles bets={bets} />

            <div className="rounded-lg border border-[#262626] bg-[#141414]">
              <div className="px-5 py-4 border-b border-[#262626] flex items-center justify-between gap-4">
                <h2 className="text-base font-semibold text-white">Bet History</h2>
                {availableSeasons.length > 0 && (
                  <Select value={seasonFilter} onValueChange={setSeasonFilter}>
                    <SelectTrigger className="h-8 w-[130px] border-[#262626] bg-[#0a0a0a] text-xs text-gray-300">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="border-[#262626] bg-[#141414]">
                      <SelectItem value="all" className="text-xs text-white focus:bg-[#1e1e1e] focus:text-white">All Seasons</SelectItem>
                      {availableSeasons.map(y => (
                        <SelectItem key={y} value={y} className="text-xs text-white focus:bg-[#1e1e1e] focus:text-white">{y} Season</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
              <div className="overflow-x-auto">
                {betsLoading ? (
                  <p className="px-5 py-8 text-sm text-gray-500">Loading bets…</p>
                ) : bets.length === 0 ? (
                  <p className="px-5 py-8 text-sm text-gray-500">No bets logged yet.</p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow className="border-b border-[#262626] hover:bg-transparent">
                        <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 whitespace-nowrap">Date</TableHead>
                        <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 whitespace-nowrap">Game</TableHead>
                        <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 whitespace-nowrap">Market</TableHead>
                        <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 text-right whitespace-nowrap">Runs</TableHead>
                        <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 whitespace-nowrap">Bookmaker</TableHead>
                        <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 text-right whitespace-nowrap">Odds</TableHead>
                        <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 text-right whitespace-nowrap">Stake</TableHead>
                        <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 whitespace-nowrap">Status</TableHead>
                        <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 text-right whitespace-nowrap">P&amp;L</TableHead>
                        <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 text-right whitespace-nowrap">EV</TableHead>
                        <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 whitespace-nowrap"></TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {bets.map(bet => {
                        const status   = outcomeToStatus(bet.outcome)
                        const ev       = fmtEv(bet.ev)
                        const pnlColor = bet.profit_loss === null
                          ? "text-gray-500"
                          : bet.profit_loss >= 0 ? "text-[#10b981]" : "text-[#ef4444]"
                        return (
                          <TableRow key={bet.bet_id} className="border-b border-[#1a1a1a] hover:bg-[#1a1a1a] transition-colors">
                            <TableCell className="px-4 py-3 text-sm text-gray-400 whitespace-nowrap">{bet.score_date}</TableCell>
                            <TableCell className="px-4 py-3 text-sm text-white whitespace-nowrap">{bet.matchup ? normalizeMatchup(bet.matchup) : "—"}</TableCell>
                            <TableCell className="px-4 py-3 text-sm text-gray-300 whitespace-nowrap">{marketDisplay(bet.market)}</TableCell>
                            <TableCell className="px-4 py-3 text-sm text-gray-300 text-right whitespace-nowrap">
                              {bet.total_line != null ? bet.total_line : "—"}
                            </TableCell>
                            <TableCell className="px-4 py-3 text-sm text-gray-400 whitespace-nowrap">{bet.bookmaker ?? "—"}</TableCell>
                            <TableCell className="px-4 py-3 text-sm text-gray-300 text-right whitespace-nowrap">{fmtOdds(bet.american_odds)}</TableCell>
                            <TableCell className="px-4 py-3 text-sm text-gray-300 text-right whitespace-nowrap">${bet.stake}</TableCell>
                            <TableCell className="px-4 py-3 whitespace-nowrap"><StatusBadge status={status} /></TableCell>
                            <TableCell className={cn("px-4 py-3 text-sm text-right font-medium whitespace-nowrap", pnlColor)}>
                              {fmtPnl(bet.profit_loss)}
                            </TableCell>
                            <TableCell className={cn("px-4 py-3 text-sm text-right whitespace-nowrap", ev.cls)}>
                              {ev.text}
                            </TableCell>
                            <TableCell className="px-4 py-3 whitespace-nowrap">
                              <div className="flex items-center gap-1.5">
                                <Button variant="ghost" size="sm"
                                  className="h-8 w-8 p-0 text-gray-500 hover:text-white hover:bg-[#1e1e1e]"
                                  onClick={() => setEditingBet(bet)}>
                                  <Pencil className="h-3.5 w-3.5" />
                                </Button>
                                <Button variant="ghost" size="sm"
                                  className="h-8 w-8 p-0 text-gray-500 hover:text-[#ef4444] hover:bg-[#1e1e1e]"
                                  onClick={() => setDeletingBetId(bet.bet_id)}>
                                  <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                              </div>
                            </TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                )}
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Delete confirmation */}
      <AlertDialog open={!!deletingBetId} onOpenChange={open => { if (!open) setDeletingBetId(null) }}>
        <AlertDialogContent className="border-[#262626] bg-[#141414] text-white">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-white">Delete this bet?</AlertDialogTitle>
            <AlertDialogDescription className="text-gray-400">
              This action cannot be undone. The bet record will be permanently removed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="border-[#262626] bg-transparent text-gray-300 hover:bg-[#1a1a1a] hover:text-white">
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              className="bg-[#ef4444] text-white hover:bg-[#dc2626]"
              onClick={() => deletingBetId && deleteMutation.mutate(deletingBetId)}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Edit modal */}
      {editingBet && (
        <EditBetModal
          bet={editingBet}
          onClose={() => setEditingBet(null)}
          onSave={patch => updateMutation.mutate({ bet_id: editingBet.bet_id, patch })}
          isSaving={updateMutation.isPending}
        />
      )}
    </div>
    </AuthGuard>
  )
}

// ---------------------------------------------------------------------------
// Default export — wraps inner component in Suspense for useSearchParams
// ---------------------------------------------------------------------------
export default function BetLogPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
        <span className="text-sm text-gray-500">Loading…</span>
      </div>
    }>
      <BetLogInner />
    </Suspense>
  )
}
