"use client"

import { useState, useMemo } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { format } from "date-fns"
import { CalendarIcon, ChevronDown, ChevronUp, ChevronsUpDown, LogOut } from "lucide-react"

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
import { cn } from "@/lib/utils"

// ---------------------------------------------------------------------------
// Mock data — replace with useQuery hook in A0.4
// ---------------------------------------------------------------------------
const MOCK_DATA = {
  bankrollDefault: 1000,
  markets: [
    { game_pk: 1001, game: "HOU @ NYM", time: "7:10 PM ET", market: "Totals Over 8.5",  marketType: "total",     side: "Over",  modelProb: 0.583, bovadaProb: 0.541, qualified: true  },
    { game_pk: 1001, game: "HOU @ NYM", time: "7:10 PM ET", market: "Totals Under 8.5", marketType: "total",     side: "Under", modelProb: 0.417, bovadaProb: 0.459, qualified: false },
    { game_pk: 1001, game: "HOU @ NYM", time: "7:10 PM ET", market: "Home ML",          marketType: "moneyline", side: "Home",  modelProb: 0.524, bovadaProb: 0.541, qualified: false },
    { game_pk: 1001, game: "HOU @ NYM", time: "7:10 PM ET", market: "Away ML",          marketType: "moneyline", side: "Away",  modelProb: 0.476, bovadaProb: 0.459, qualified: false },
    { game_pk: 1002, game: "LAD @ SF",  time: "9:45 PM ET", market: "Home ML",          marketType: "moneyline", side: "Home",  modelProb: 0.612, bovadaProb: 0.571, qualified: true  },
    { game_pk: 1002, game: "LAD @ SF",  time: "9:45 PM ET", market: "Away ML",          marketType: "moneyline", side: "Away",  modelProb: 0.388, bovadaProb: 0.429, qualified: false },
    { game_pk: 1002, game: "LAD @ SF",  time: "9:45 PM ET", market: "Totals Over 7.5",  marketType: "total",     side: "Over",  modelProb: 0.531, bovadaProb: 0.510, qualified: true  },
    { game_pk: 1002, game: "LAD @ SF",  time: "9:45 PM ET", market: "Totals Under 7.5", marketType: "total",     side: "Under", modelProb: 0.469, bovadaProb: 0.490, qualified: false },
    { game_pk: 1003, game: "ATL @ PHI", time: "7:05 PM ET", market: "Away ML",          marketType: "moneyline", side: "Away",  modelProb: 0.534, bovadaProb: 0.502, qualified: true  },
    { game_pk: 1003, game: "ATL @ PHI", time: "7:05 PM ET", market: "Home ML",          marketType: "moneyline", side: "Home",  modelProb: 0.466, bovadaProb: 0.498, qualified: false },
    { game_pk: 1003, game: "ATL @ PHI", time: "7:05 PM ET", market: "Totals Over 8.0",  marketType: "total",     side: "Over",  modelProb: 0.498, bovadaProb: 0.510, qualified: false },
    { game_pk: 1004, game: "NYY @ BOS", time: "7:10 PM ET", market: "Totals Under 8.0", marketType: "total",     side: "Under", modelProb: 0.481, bovadaProb: 0.510, qualified: false },
    { game_pk: 1004, game: "NYY @ BOS", time: "7:10 PM ET", market: "Home ML",          marketType: "moneyline", side: "Home",  modelProb: 0.523, bovadaProb: 0.541, qualified: false },
    { game_pk: 1005, game: "CHC @ MIL", time: "8:10 PM ET", market: "Home ML",          marketType: "moneyline", side: "Home",  modelProb: 0.498, bovadaProb: 0.519, qualified: false },
    { game_pk: 1005, game: "CHC @ MIL", time: "8:10 PM ET", market: "Totals Over 7.5",  marketType: "total",     side: "Over",  modelProb: 0.541, bovadaProb: 0.510, qualified: true  },
  ],
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type SortKey =
  | "game"
  | "market"
  | "side"
  | "modelProb"
  | "bovadaProb"
  | "edge"
  | "ev"
  | "rawKelly"
  | "cappedKelly"
  | "stake"

type SortDir = "asc" | "desc"

interface ComputedRow {
  game_pk: number
  game: string
  time: string
  market: string
  marketType: string
  side: string
  modelProb: number
  bovadaProb: number
  qualified: boolean
  edge: number
  ev: number
  rawKelly: number
  cappedKelly: number
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function pct(v: number) {
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`
}
function pctRaw(v: number) {
  return `${(v * 100).toFixed(1)}%`
}
function usd(v: number) {
  return `$${v.toFixed(2)}`
}

function computeRow(m: (typeof MOCK_DATA.markets)[0]): ComputedRow {
  const edge = m.modelProb - m.bovadaProb
  const ev = m.modelProb * (1 / m.bovadaProb - 1) - (1 - m.modelProb)
  const rawKelly = ((m.modelProb - m.bovadaProb) / (1 - m.bovadaProb)) * 100
  const cappedKelly = Math.min(Math.max(rawKelly, 0), 5)
  return { ...m, edge, ev, rawKelly, cappedKelly }
}

const COMPUTED_ROWS: ComputedRow[] = MOCK_DATA.markets.map(computeRow)

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
          <Button
            variant="ghost"
            size="sm"
            className="text-gray-400 hover:text-white hover:bg-[#141414]"
            asChild
          >
            <Link href="/">
              <LogOut className="mr-1.5 h-3.5 w-3.5" />
              Sign Out
            </Link>
          </Button>
        </div>
      </div>
      {/* Sub-nav — all inactive; EV Tracker accessed from dashboard */}
      <div className="mx-auto flex max-w-6xl gap-6 px-4 pb-0">
        <Link
          href="/dashboard"
          className="border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
        >
          Dashboard
        </Link>
        <Link
          href="/performance"
          className="border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
        >
          Performance
        </Link>
        <Link
          href="/settings"
          className="border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
        >
          Settings
        </Link>
      </div>
    </nav>
  )
}

// ---------------------------------------------------------------------------
// Sort indicator icon
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
  const cls =
    type === "total"
      ? "bg-teal-950 text-teal-400 border-teal-800"
      : "bg-blue-950 text-blue-400 border-blue-800"
  return (
    <Badge
      variant="outline"
      className={cn("text-[10px] font-medium uppercase tracking-wide border px-1.5 py-0", cls)}
    >
      {label}
    </Badge>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function EVTrackerPage() {
  const router = useRouter()
  const [date, setDate] = useState<Date>(new Date(2026, 5, 5)) // Jun 5 2026
  const [calOpen, setCalOpen] = useState(false)
  const [bankroll, setBankroll] = useState<number>(MOCK_DATA.bankrollDefault)
  const [sortKey, setSortKey] = useState<SortKey>("edge")
  const [sortDir, setSortDir] = useState<SortDir>("desc")

  // Derived summary values
  const qualifiedCount = COMPUTED_ROWS.filter((r) => r.qualified).length
  const totalCount = COMPUTED_ROWS.length
  const estDailyEV = COMPUTED_ROWS.filter((r) => r.qualified).reduce((acc, r) => {
    const stake = (Math.min(Math.max(r.rawKelly, 0), 5) / 100) * bankroll
    return acc + r.ev * stake
  }, 0)

  // Sorted rows
  const sorted = useMemo(() => {
    return [...COMPUTED_ROWS].sort((a, b) => {
      let av: number | string
      let bv: number | string
      switch (sortKey) {
        case "game":      av = a.game;        bv = b.game;        break
        case "market":    av = a.market;      bv = b.market;      break
        case "side":      av = a.side;        bv = b.side;        break
        case "modelProb": av = a.modelProb;   bv = b.modelProb;   break
        case "bovadaProb":av = a.bovadaProb;  bv = b.bovadaProb;  break
        case "edge":      av = a.edge;        bv = b.edge;        break
        case "ev":        av = a.ev;          bv = b.ev;          break
        case "rawKelly":  av = a.rawKelly;    bv = b.rawKelly;    break
        case "cappedKelly":av= a.cappedKelly; bv = b.cappedKelly; break
        case "stake":
          av = (a.cappedKelly / 100) * bankroll
          bv = (b.cappedKelly / 100) * bankroll
          break
        default:          av = a.edge;        bv = b.edge
      }
      if (typeof av === "string" && typeof bv === "string") {
        return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av)
      }
      return sortDir === "asc"
        ? (av as number) - (bv as number)
        : (bv as number) - (av as number)
    })
  }, [sortKey, sortDir, bankroll])

  function handleSort(col: SortKey) {
    if (col === sortKey) {
      // cycle: asc → desc → reset to default (edge desc)
      if (sortDir === "asc") {
        setSortDir("desc")
      } else {
        setSortKey("edge")
        setSortDir("desc")
      }
    } else {
      setSortKey(col)
      setSortDir("desc")
    }
  }

  function handleBankrollChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = parseFloat(e.target.value)
    setBankroll(isNaN(val) ? 0 : val)
  }

  function buildLogBetUrl(row: ComputedRow) {
    const params = new URLSearchParams({
      game_pk: String(row.game_pk),
      market: row.market,
      side: row.side,
      modelProb: String(row.modelProb),
      bovadaProb: String(row.bovadaProb),
    })
    return `/bet-log?${params.toString()}`
  }

  const thCls =
    "cursor-pointer select-none whitespace-nowrap text-xs font-medium text-gray-500 uppercase tracking-wide hover:text-gray-300 transition-colors px-3 py-3"

  return (
    <div className="min-h-screen bg-[#0a0a0a] font-sans text-white">
      <Navbar />

      <main className="mx-auto max-w-6xl px-4 py-8">
        {/* ----------------------------------------------------------------
            Page header
        ---------------------------------------------------------------- */}
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">EV Tracker</h1>
            <p className="mt-0.5 text-sm text-gray-500">
              All markets · Kelly-sized stakes · Full model transparency
            </p>
          </div>

          {/* Controls */}
          <div className="flex items-center gap-4">
            {/* Date picker */}
            <Popover open={calOpen} onOpenChange={setCalOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  className="w-[160px] justify-start gap-2 border-[#262626] bg-[#141414] text-left text-sm font-normal text-white hover:bg-[#1a1a1a]"
                >
                  <CalendarIcon className="h-4 w-4 text-gray-500" />
                  {format(date, "MMM d, yyyy")}
                </Button>
              </PopoverTrigger>
              <PopoverContent
                className="w-auto border-[#262626] bg-[#141414] p-0"
                align="end"
              >
                <Calendar
                  mode="single"
                  selected={date}
                  onSelect={(d) => {
                    if (d) { setDate(d); setCalOpen(false) }
                  }}
                  initialFocus
                />
              </PopoverContent>
            </Popover>

            {/* Bankroll input */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">Bankroll</span>
              <div className="flex items-center rounded-md border border-[#262626] bg-[#141414] px-2.5">
                <span className="text-sm text-gray-500">$</span>
                <input
                  type="number"
                  min={0}
                  step={100}
                  value={bankroll}
                  onChange={handleBankrollChange}
                  className="w-24 bg-transparent py-1.5 pl-1 text-sm text-white outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                />
              </div>
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
              <span className="text-gray-500"> total markets today</span>
            </span>
            <span className="text-gray-700">·</span>
            <span>
              <span className="text-gray-500">Est. daily EV: </span>
              <span
                className={cn(
                  "font-semibold",
                  estDailyEV >= 0 ? "text-[#10b981]" : "text-[#ef4444]"
                )}
              >
                {estDailyEV >= 0 ? "+" : ""}${estDailyEV.toFixed(2)}
              </span>
            </span>
          </div>
        </div>

        {/* ----------------------------------------------------------------
            Main EV table
        ---------------------------------------------------------------- */}
        <div className="rounded-xl border border-[#262626] bg-[#141414]">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-b border-[#262626] hover:bg-transparent">
                  <TableHead className={thCls} onClick={() => handleSort("game")}>
                    Game <SortIcon col="game" sortKey={sortKey} sortDir={sortDir} />
                  </TableHead>
                  <TableHead className={thCls} onClick={() => handleSort("market")}>
                    Market <SortIcon col="market" sortKey={sortKey} sortDir={sortDir} />
                  </TableHead>
                  <TableHead className={thCls} onClick={() => handleSort("side")}>
                    Side <SortIcon col="side" sortKey={sortKey} sortDir={sortDir} />
                  </TableHead>
                  <TableHead className={cn(thCls, "text-right")} onClick={() => handleSort("modelProb")}>
                    Model% <SortIcon col="modelProb" sortKey={sortKey} sortDir={sortDir} />
                  </TableHead>
                  <TableHead className={cn(thCls, "text-right")} onClick={() => handleSort("bovadaProb")}>
                    Bovada% <SortIcon col="bovadaProb" sortKey={sortKey} sortDir={sortDir} />
                  </TableHead>
                  <TableHead className={cn(thCls, "text-right")} onClick={() => handleSort("edge")}>
                    Edge <SortIcon col="edge" sortKey={sortKey} sortDir={sortDir} />
                  </TableHead>
                  <TableHead className={cn(thCls, "text-right")} onClick={() => handleSort("ev")}>
                    EV <SortIcon col="ev" sortKey={sortKey} sortDir={sortDir} />
                  </TableHead>
                  <TableHead className={cn(thCls, "text-right")} onClick={() => handleSort("rawKelly")}>
                    Raw Kelly% <SortIcon col="rawKelly" sortKey={sortKey} sortDir={sortDir} />
                  </TableHead>
                  <TableHead className={cn(thCls, "text-right")} onClick={() => handleSort("cappedKelly")}>
                    Capped Kelly% <SortIcon col="cappedKelly" sortKey={sortKey} sortDir={sortDir} />
                  </TableHead>
                  <TableHead className={cn(thCls, "text-right")} onClick={() => handleSort("stake")}>
                    Stake ($) <SortIcon col="stake" sortKey={sortKey} sortDir={sortDir} />
                  </TableHead>
                  <TableHead className={cn(thCls, "text-center")}>
                    Action
                  </TableHead>
                </TableRow>
              </TableHeader>

              <TableBody>
                {sorted.map((row, i) => {
                  const stake = (row.cappedKelly / 100) * bankroll
                  const isQualified = row.qualified

                  return (
                    <TableRow
                      key={`${row.game_pk}-${row.market}-${row.side}`}
                      onClick={() => isQualified && router.push(`/picks/${row.game_pk}`)}
                      className={cn(
                        "border-b border-[#262626] transition-colors",
                        isQualified
                          ? "cursor-pointer border-l-2 border-l-[#10b981] hover:bg-[#10b98108]"
                          : "cursor-default opacity-60",
                        i === sorted.length - 1 && "border-b-0"
                      )}
                    >
                      {/* Game */}
                      <TableCell className="py-3 pl-4 pr-3">
                        <p className="text-sm font-medium text-white">{row.game}</p>
                        <p className="text-xs text-gray-500">{row.time}</p>
                      </TableCell>

                      {/* Market */}
                      <TableCell className="px-3 py-3">
                        <MarketBadge type={row.marketType} label={row.market} />
                      </TableCell>

                      {/* Side */}
                      <TableCell className="px-3 py-3 text-sm text-gray-400">
                        {row.side}
                      </TableCell>

                      {/* Model% */}
                      <TableCell className={cn(
                        "px-3 py-3 text-right text-sm font-medium",
                        row.edge > 0 ? "text-[#10b981]" : "text-gray-400"
                      )}>
                        {pctRaw(row.modelProb)}
                      </TableCell>

                      {/* Bovada% */}
                      <TableCell className="px-3 py-3 text-right text-sm text-gray-400">
                        {pctRaw(row.bovadaProb)}
                      </TableCell>

                      {/* Edge */}
                      <TableCell className={cn(
                        "px-3 py-3 text-right text-sm font-semibold",
                        row.edge > 0 ? "text-[#10b981]" : "text-[#ef4444]"
                      )}>
                        {pct(row.edge)}
                      </TableCell>

                      {/* EV */}
                      <TableCell className={cn(
                        "px-3 py-3 text-right text-sm font-semibold",
                        row.ev > 0 ? "text-[#10b981]" : "text-[#ef4444]"
                      )}>
                        {pct(row.ev)}
                      </TableCell>

                      {/* Raw Kelly% */}
                      <TableCell className="px-3 py-3 text-right text-sm text-gray-400">
                        {row.rawKelly >= 0 ? `+${row.rawKelly.toFixed(1)}%` : `${row.rawKelly.toFixed(1)}%`}
                      </TableCell>

                      {/* Capped Kelly% */}
                      <TableCell className="px-3 py-3 text-right text-sm text-gray-400">
                        {row.cappedKelly.toFixed(1)}%
                      </TableCell>

                      {/* Stake */}
                      <TableCell className={cn(
                        "px-3 py-3 text-right text-sm font-medium",
                        isQualified ? "text-[#10b981]" : "text-gray-400"
                      )}>
                        {usd(stake)}
                      </TableCell>

                      {/* Action */}
                      <TableCell className="px-3 py-3 text-center">
                        {isQualified ? (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation()
                              router.push(buildLogBetUrl(row))
                            }}
                            className="h-7 border-[#10b981] bg-transparent px-2.5 text-[11px] font-medium text-[#10b981] hover:bg-[#10b98115] hover:text-[#10b981]"
                          >
                            Log Bet
                          </Button>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </div>

        {/* Footer note */}
        <p className="mt-4 text-center text-xs text-gray-600">
          Kelly stakes capped at 5% max bankroll per bet. EV and Kelly calculated from model vs. Bovada implied probabilities. Not financial advice.
        </p>
      </main>
    </div>
  )
}
