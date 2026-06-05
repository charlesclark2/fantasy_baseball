"use client"

import React, { Suspense, useState, useEffect } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { format, isAfter, startOfDay, parseISO } from "date-fns"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { CalendarIcon, CheckCircle, LogOut } from "lucide-react"
import { cn } from "@/lib/utils"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type BetStatus = "Won" | "Lost" | "Open" | "Push"

interface Bet {
  id: string
  date: string       // "Jun 4" display string — also used to determine game date
  dateIso: string    // ISO date for date comparison logic
  game: string
  market: string
  bookmaker: string
  side: string
  odds: number
  stake: number
  status: BetStatus
  clv: number | null
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const TODAY = startOfDay(new Date()) // Jun 5 2026

const MOCK_DATA = {
  games: [
    { game_pk: 1001, label: "HOU @ NYM — 7:10 PM ET" },
    { game_pk: 1002, label: "LAD @ SF — 9:45 PM ET" },
    { game_pk: 1003, label: "ATL @ PHI — 7:05 PM ET" },
    { game_pk: 1004, label: "NYY @ BOS — 7:10 PM ET" },
    { game_pk: 1005, label: "CHC @ MIL — 8:10 PM ET" },
  ],
  initialBets: [
    { id: "1", date: "Jun 4", dateIso: "2026-06-04", game: "NYY @ BOS",  market: "Totals Under 8.0", bookmaker: "Bovada", side: "Under", odds: -118, stake: 50, status: "Won"  as BetStatus, clv: 0.018 },
    { id: "2", date: "Jun 4", dateIso: "2026-06-04", game: "LAD @ SF",   market: "Home ML",          bookmaker: "Bovada", side: "Home",  odds: -133, stake: 50, status: "Lost" as BetStatus, clv: 0.033 },
    { id: "3", date: "Jun 3", dateIso: "2026-06-03", game: "HOU @ NYM",  market: "Totals Over 8.5",  bookmaker: "Bovada", side: "Over",  odds: -118, stake: 75, status: "Won"  as BetStatus, clv: 0.038 },
    { id: "4", date: "Jun 3", dateIso: "2026-06-03", game: "ATL @ PHI",  market: "Away ML",          bookmaker: "Bovada", side: "Away",  odds: -101, stake: 50, status: "Won"  as BetStatus, clv: 0.021 },
    { id: "5", date: "Jun 2", dateIso: "2026-06-02", game: "CHC @ MIL",  market: "Totals Over 7.5",  bookmaker: "Bovada", side: "Over",  odds: -104, stake: 50, status: "Lost" as BetStatus, clv: -0.011 },
    { id: "6", date: "Jun 1", dateIso: "2026-06-01", game: "SEA @ TEX",  market: "Home ML",          bookmaker: "Bovada", side: "Home",  odds: -119, stake: 50, status: "Push" as BetStatus, clv: 0.014 },
    { id: "7", date: "Jun 1", dateIso: "2026-06-01", game: "NYM @ WSH",  market: "Totals Under 7.0", bookmaker: "Bovada", side: "Under", odds: -118, stake: 50, status: "Open" as BetStatus, clv: null },
  ] as Bet[],
}

const MARKET_OPTIONS = [
  "Totals Over 8.5",
  "Totals Under 8.5",
  "Home ML",
  "Away ML",
  "Totals Over 7.5",
  "Totals Under 7.5",
  "Totals Over 8.0",
  "Totals Under 8.0",
]

const BOOKMAKER_OPTIONS = ["Bovada", "DraftKings", "FanDuel", "BetMGM", "Pinnacle", "Other"]

// Returns the filtered side options based on the currently selected market
function sideOptionsFor(market: string): string[] {
  if (!market) return ["Over", "Under", "Home", "Away"]
  const m = market.toLowerCase()
  if (m.includes("over") || m.includes("under") || m.includes("totals")) return ["Over", "Under"]
  if (m.includes("ml") || m.includes("moneyline") || m.includes("home") || m.includes("away")) return ["Home", "Away"]
  return ["Over", "Under", "Home", "Away"]
}

// Auto-derive side when market changes
function sideFromMarket(market: string): string {
  if (market.includes("Over")) return "Over"
  if (market.includes("Under")) return "Under"
  if (market.includes("Home")) return "Home"
  if (market.includes("Away")) return "Away"
  return ""
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function probToAmerican(prob: number): number {
  if (prob >= 0.5) return Math.round(-(prob / (1 - prob)) * 100)
  return Math.round(((1 - prob) / prob) * 100)
}

function calcPnl(status: BetStatus, stake: number, odds: number): number | null {
  if (status === "Open") return null
  if (status === "Lost") return -stake
  if (status === "Push") return 0
  if (odds < 0) return Math.round((stake / (Math.abs(odds) / 100)) * 100) / 100
  return Math.round(stake * (odds / 100) * 100) / 100
}

function fmtPnl(val: number | null): string {
  if (val === null) return "—"
  const sign = val >= 0 ? "+" : ""
  return `${sign}$${Math.abs(val).toFixed(2)}`
}

function fmtOdds(odds: number): string {
  return odds > 0 ? `+${odds}` : String(odds)
}

function fmtClv(clv: number | null): { text: string; cls: string } {
  if (clv === null) return { text: "—", cls: "text-gray-600" }
  const sign = clv >= 0 ? "+" : ""
  return {
    text: `${sign}${(clv * 100).toFixed(1)}%`,
    cls: clv >= 0 ? "text-[#10b981]" : "text-[#ef4444]",
  }
}

// A bet is settleable if it's Open AND the game date is strictly before today
function isSettleable(bet: Bet): boolean {
  if (bet.status !== "Open") return false
  const gameDay = startOfDay(parseISO(bet.dateIso))
  return isAfter(TODAY, gameDay) // today > game date → game has been played
}

// ---------------------------------------------------------------------------
// Navbar
// ---------------------------------------------------------------------------
function Navbar() {
  return (
    <nav className="sticky top-0 z-50 border-b border-[#262626] bg-[#0a0a0a]/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        <Link href="/" className="flex items-center gap-0 text-lg font-bold tracking-tight">
          <span className="text-[#10b981]">Credence</span>
          <span className="text-white"> Sports</span>
        </Link>
        <div className="flex items-center gap-3">
          <span className="hidden text-xs text-gray-500 sm:block">user@example.com</span>
          <Button variant="ghost" size="sm" className="text-gray-400 hover:text-white hover:bg-[#141414]" asChild>
            <Link href="/">
              <LogOut className="mr-1.5 h-3.5 w-3.5" />
              Sign Out
            </Link>
          </Button>
        </div>
      </div>
      {/* Sub-nav — Bet Log active */}
      <div className="mx-auto flex max-w-6xl gap-6 px-4 pb-0">
        <Link href="/dashboard"   className="border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors">Dashboard</Link>
        <Link href="/performance" className="border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors">Performance</Link>
        <Link href="/settings"    className="border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors">Settings</Link>
        <Link href="/bet-log"     className="border-b-2 border-[#10b981] pb-2.5 text-sm text-white font-medium transition-colors">Bet Log</Link>
      </div>
    </nav>
  )
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------
function StatusBadge({ status }: { status: BetStatus }) {
  if (status === "Won")  return <Badge className="bg-[#10b981] text-[#0a0a0a] text-xs font-semibold">Won</Badge>
  if (status === "Lost") return <Badge className="bg-[#ef4444] text-white text-xs font-semibold">Lost</Badge>
  if (status === "Push") return <Badge variant="outline" className="border-[#f59e0b] text-[#f59e0b] text-xs">Push</Badge>
  return <Badge variant="outline" className="border-[#404040] text-gray-400 text-xs">Open</Badge>
}

// ---------------------------------------------------------------------------
// Summary tiles
// ---------------------------------------------------------------------------
function SummaryTiles({ bets }: { bets: Bet[] }) {
  const settled = bets.filter((b) => b.status !== "Open")
  const won = bets.filter((b) => b.status === "Won")
  const netPnl = settled.reduce((acc, b) => acc + (calcPnl(b.status, b.stake, b.odds) ?? 0), 0)
  const totalStaked = settled.reduce((acc, b) => acc + b.stake, 0)
  const roi = totalStaked > 0 ? (netPnl / totalStaked) * 100 : 0
  const winRate = settled.length > 0 ? (won.length / settled.length) * 100 : 0

  const tiles = [
    { label: "Net P&L",  value: fmtPnl(netPnl),                               positive: netPnl >= 0 },
    { label: "ROI",      value: `${roi >= 0 ? "+" : ""}${roi.toFixed(1)}%`,    positive: roi >= 0 },
    { label: "Win Rate", value: `${winRate.toFixed(1)}%`,                       positive: winRate >= 50 },
  ]

  return (
    <div className="grid grid-cols-3 gap-4 mb-6">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-lg border border-[#262626] bg-[#141414] px-5 py-4">
          <p className="text-xs text-gray-500 mb-1">{t.label}</p>
          <p className={cn("text-xl font-bold", t.positive ? "text-[#10b981]" : "text-[#ef4444]")}>{t.value}</p>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Inner page — uses useSearchParams so must be inside Suspense
// ---------------------------------------------------------------------------
function BetLogInner() {
  const searchParams = useSearchParams()

  const qGamePk     = searchParams.get("game_pk")    ? Number(searchParams.get("game_pk"))    : null
  const qMarket     = searchParams.get("market")     ?? ""
  const qSide       = searchParams.get("side")       ?? ""
  const qModelProb  = searchParams.get("modelProb")  ? Number(searchParams.get("modelProb"))  : null
  const qBovadaProb = searchParams.get("bovadaProb") ? Number(searchParams.get("bovadaProb")) : null

  const prefillGame = qGamePk ? MOCK_DATA.games.find((g) => g.game_pk === qGamePk) : null
  const isPrefilled = !!prefillGame

  // Form state
  const [date, setDate]             = useState<Date>(new Date())
  const [calOpen, setCalOpen]       = useState(false)
  const [game, setGame]             = useState(prefillGame?.label ?? "")
  const [market, setMarket]         = useState(qMarket)
  const [bookmaker, setBookmaker]   = useState("Bovada")
  const [side, setSide]             = useState(qSide)
  const [odds, setOdds]             = useState(qBovadaProb != null ? String(probToAmerican(qBovadaProb)) : "")
  const [stake, setStake]           = useState("")
  const [notes, setNotes]           = useState("")
  const [saveSuccess, setSaveSuccess] = useState(false)

  // Sync side when market changes
  useEffect(() => {
    if (market) setSide(sideFromMarket(market))
  }, [market])

  const sideOptions = sideOptionsFor(market)

  // Bet history
  const [bets, setBets]             = useState<Bet[]>(MOCK_DATA.initialBets)
  const [settlingId, setSettlingId] = useState<string | null>(null)

  function handleSave() {
    if (!game || !market || !side || !odds || !stake) return
    const newBet: Bet = {
      id: Date.now().toString(),
      date: format(date, "MMM d"),
      dateIso: format(date, "yyyy-MM-dd"),
      game: game.split(" — ")[0],
      market,
      bookmaker,
      side,
      odds: Number(odds),
      stake: Number(stake),
      status: "Open",
      clv: null,
    }
    setBets((prev) => [newBet, ...prev])
    setGame(prefillGame?.label ?? "")
    setMarket(qMarket)
    setBookmaker("Bovada")
    setSide(qSide)
    setOdds(qBovadaProb != null ? String(probToAmerican(qBovadaProb)) : "")
    setStake("")
    setNotes("")
    setSaveSuccess(true)
    setTimeout(() => setSaveSuccess(false), 2000)
  }

  function handleSettle(id: string, result: "Won" | "Lost" | "Push") {
    setBets((prev) => prev.map((b) => (b.id === id ? { ...b, status: result } : b)))
    setSettlingId(null)
  }

  const edge = qModelProb != null && qBovadaProb != null
    ? ((qModelProb - qBovadaProb) * 100).toFixed(1)
    : null

  return (
    // Fix 1: overflow-x-hidden + w-full on outermost container
    <div className="min-h-screen w-full overflow-x-hidden bg-[#0a0a0a]">
      <Navbar />

      <main className="mx-auto max-w-6xl px-4 py-8">
        {/* Page header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-white">Bet Log</h1>
          <p className="mt-1 text-sm text-gray-500">Track your actual bets against the model&apos;s predictions.</p>
        </div>

        <div className="flex flex-col gap-8">
          {/* ----------------------------------------------------------------
              Log a Bet form — full width row above the table
          ---------------------------------------------------------------- */}
          <div className="rounded-lg border border-[#262626] bg-[#141414] p-6">
            <h2 className="mb-5 text-base font-semibold text-white">Log a Bet</h2>

            {isPrefilled && (
              <div className="mb-5 rounded-md border border-[#10b981]/30 bg-[#10b981]/10 px-3 py-2 text-xs text-[#10b981]">
                Pre-filled from EV Tracker &mdash; {prefillGame!.label.split(" — ")[0]}, {qMarket || "—"}
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
                    <Calendar mode="single" selected={date} onSelect={(d) => { if (d) { setDate(d); setCalOpen(false) } }} initialFocus />
                  </PopoverContent>
                </Popover>
              </div>

              {/* Game */}
              <div className="flex flex-col gap-1.5 col-span-1 sm:col-span-2">
                <Label className="text-xs text-gray-400">Game</Label>
                <Select value={game} onValueChange={setGame}>
                  <SelectTrigger className="border-[#262626] bg-[#0a0a0a] text-sm text-white">
                    <SelectValue placeholder="Select game…" />
                  </SelectTrigger>
                  <SelectContent className="border-[#262626] bg-[#141414]">
                    {MOCK_DATA.games.map((g) => (
                      <SelectItem key={g.game_pk} value={g.label} className="text-sm text-white focus:bg-[#1e1e1e] focus:text-white">{g.label}</SelectItem>
                    ))}
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
                    {MARKET_OPTIONS.map((m) => (
                      <SelectItem key={m} value={m} className="text-sm text-white focus:bg-[#1e1e1e] focus:text-white">{m}</SelectItem>
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
                    {BOOKMAKER_OPTIONS.map((b) => (
                      <SelectItem key={b} value={b} className="text-sm text-white focus:bg-[#1e1e1e] focus:text-white">{b}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Side */}
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">Side</Label>
                <Select value={side} onValueChange={setSide}>
                  <SelectTrigger className="border-[#262626] bg-[#0a0a0a] text-sm text-white">
                    <SelectValue placeholder="Select side…" />
                  </SelectTrigger>
                  <SelectContent className="border-[#262626] bg-[#141414]">
                    {sideOptions.map((s) => (
                      <SelectItem key={s} value={s} className="text-sm text-white focus:bg-[#1e1e1e] focus:text-white">{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Odds + Stake inline */}
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">Odds (American)</Label>
                <Input
                  type="number"
                  placeholder="-110"
                  value={odds}
                  onChange={(e) => setOdds(e.target.value)}
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
                  min={1}
                  value={stake}
                  onChange={(e) => setStake(e.target.value)}
                  className="border-[#262626] bg-[#0a0a0a] text-sm text-white placeholder:text-gray-600"
                />
              </div>
              <div className="flex flex-col gap-1.5 flex-1 min-w-[180px]">
                <Label className="text-xs text-gray-400">Notes (optional)</Label>
                <Input
                  placeholder="Any context about this bet..."
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="border-[#262626] bg-[#0a0a0a] text-sm text-white placeholder:text-gray-600"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Button
                  className="bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669] px-8"
                  onClick={handleSave}
                  disabled={!game || !market || !side || !odds || !stake}
                >
                  Save Bet
                </Button>
              </div>
              {saveSuccess && (
                <div className="flex items-center gap-2 text-xs text-[#10b981] pb-0.5">
                  <CheckCircle className="h-3.5 w-3.5" />
                  Bet logged successfully
                </div>
              )}
            </div>

            {qModelProb != null && qBovadaProb != null && (
              <p className="mt-3 text-xs text-gray-500">
                Model probability: <span className="text-gray-300">{(qModelProb * 100).toFixed(1)}%</span>
                {" · "}Bovada: <span className="text-gray-300">{(qBovadaProb * 100).toFixed(1)}%</span>
                {" · "}Edge: <span className="text-[#10b981]">+{edge}%</span>
              </p>
            )}
          </div>

          {/* ----------------------------------------------------------------
              Summary tiles + bet history — full width
          ---------------------------------------------------------------- */}
          <div className="flex flex-col gap-0 min-w-0">
            <SummaryTiles bets={bets} />

            <div className="rounded-lg border border-[#262626] bg-[#141414]">
              <div className="px-5 py-4 border-b border-[#262626]">
                <h2 className="text-base font-semibold text-white">Bet History</h2>
              </div>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="border-b border-[#262626] hover:bg-transparent">
                      <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 whitespace-nowrap">Date</TableHead>
                      <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 whitespace-nowrap">Game</TableHead>
                      <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 whitespace-nowrap">Market</TableHead>
                      <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 whitespace-nowrap">Bookmaker</TableHead>
                      <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 whitespace-nowrap">Side</TableHead>
                      <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 text-right whitespace-nowrap">Odds</TableHead>
                      <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 text-right whitespace-nowrap">Stake</TableHead>
                      <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 whitespace-nowrap">Status</TableHead>
                      <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 text-right whitespace-nowrap">P&amp;L</TableHead>
                      <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 text-right whitespace-nowrap">CLV</TableHead>
                      <TableHead className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 whitespace-nowrap">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {bets.map((bet) => {
                      const pnl = calcPnl(bet.status, bet.stake, bet.odds)
                      const clv = fmtClv(bet.clv)
                      const settleable = isSettleable(bet)
                      const isSettling = settlingId === bet.id
                      const pnlColor = pnl === null ? "text-gray-500" : pnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"

                      return (
                        <React.Fragment key={bet.id}>
                          <TableRow
                            className="border-b border-[#1a1a1a] hover:bg-[#1a1a1a] transition-colors"
                          >
                            <TableCell className="px-4 py-3 text-sm text-gray-400 whitespace-nowrap">{bet.date}</TableCell>
                            <TableCell className="px-4 py-3 text-sm text-white whitespace-nowrap">{bet.game}</TableCell>
                            <TableCell className="px-4 py-3 text-sm text-gray-300 whitespace-nowrap">{bet.market}</TableCell>
                            <TableCell className="px-4 py-3 text-sm text-gray-400 whitespace-nowrap">{bet.bookmaker}</TableCell>
                            <TableCell className="px-4 py-3 text-sm text-gray-300 whitespace-nowrap">{bet.side}</TableCell>
                            <TableCell className="px-4 py-3 text-sm text-gray-300 text-right whitespace-nowrap">{fmtOdds(bet.odds)}</TableCell>
                            <TableCell className="px-4 py-3 text-sm text-gray-300 text-right whitespace-nowrap">${bet.stake}</TableCell>
                            <TableCell className="px-4 py-3 whitespace-nowrap"><StatusBadge status={bet.status} /></TableCell>
                            <TableCell className={cn("px-4 py-3 text-sm text-right font-medium whitespace-nowrap", pnlColor)}>{fmtPnl(pnl)}</TableCell>
                            <TableCell className={cn("px-4 py-3 text-sm text-right whitespace-nowrap", clv.cls)}>{clv.text}</TableCell>
                            <TableCell className="px-4 py-3 whitespace-nowrap">
                              {/* Open + game in the past → Settle button */}
                              {settleable && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 px-2 text-xs text-gray-400 hover:text-white hover:bg-[#262626]"
                                  onClick={() => setSettlingId(isSettling ? null : bet.id)}
                                >
                                  {isSettling ? "Cancel" : "Settle"}
                                </Button>
                              )}
                              {/* Open + game today or future → Pending */}
                              {!settleable && bet.status === "Open" && (
                                <Badge variant="outline" className="border-[#404040] text-gray-500 text-xs">
                                  Pending
                                </Badge>
                              )}
                            </TableCell>
                          </TableRow>

                          {/* Inline settle selector sub-row */}
                          {isSettling && (
                            <TableRow key={`${bet.id}-settle`} className="border-b border-[#1a1a1a] bg-[#111]">
                              <TableCell colSpan={11} className="px-4 py-2">
                                <div className="flex items-center gap-2">
                                  <span className="text-xs text-gray-500 mr-1">Mark as:</span>
                                  <Button size="sm" className="h-7 px-3 text-xs bg-[#10b981] text-[#0a0a0a] hover:bg-[#059669]" onClick={() => handleSettle(bet.id, "Won")}>Won</Button>
                                  <Button size="sm" className="h-7 px-3 text-xs bg-[#ef4444] text-white hover:bg-[#dc2626]" onClick={() => handleSettle(bet.id, "Lost")}>Lost</Button>
                                  <Button size="sm" variant="outline" className="h-7 px-3 text-xs border-[#f59e0b] text-[#f59e0b] hover:bg-[#f59e0b]/10" onClick={() => handleSettle(bet.id, "Push")}>Push</Button>
                                </div>
                              </TableCell>
                            </TableRow>
                          )}
                        </React.Fragment>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
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
