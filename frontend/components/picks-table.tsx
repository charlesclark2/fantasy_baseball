"use client"

import { useState, useEffect } from "react"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { ChevronDown, ArrowUp, ArrowDown, ArrowRight, ChevronRight, Clock, Info } from "lucide-react"
import { cn } from "@/lib/utils"
import { CompactProbabilityBar } from "@/components/compact-probability-bar"

interface Pick {
  id: string
  game: string
  gameTime: string
  market: string
  marketType: "totals" | "moneyline"
  modelProb: number
  bovadaProb: number
  ciLow: number
  ciHigh: number
  conviction: "HIGH" | "MED" | "LOW"
  startTime: Date
  qualified: boolean
}

const mockPicks: Pick[] = [
  {
    id: "1",
    game: "HOU @ NYM",
    gameTime: "7:10 PM ET",
    market: "Totals Over 8.5",
    marketType: "totals",
    modelProb: 58.3,
    bovadaProb: 54.1,
    ciLow: 0.51,
    ciHigh: 0.61,
    conviction: "HIGH",
    startTime: new Date(Date.now() + 2 * 60 * 60 * 1000 + 14 * 60 * 1000),
    qualified: true,
  },
  {
    id: "2",
    game: "LAD @ SF",
    gameTime: "9:45 PM ET",
    market: "Home ML",
    marketType: "moneyline",
    modelProb: 62.1,
    bovadaProb: 55.8,
    ciLow: 0.55,
    ciHigh: 0.68,
    conviction: "HIGH",
    startTime: new Date(Date.now() + 4 * 60 * 60 * 1000 + 49 * 60 * 1000),
    qualified: true,
  },
  {
    id: "3",
    game: "ATL @ PHI",
    gameTime: "6:40 PM ET",
    market: "Totals Under 9.0",
    marketType: "totals",
    modelProb: 57.2,
    bovadaProb: 52.3,
    ciLow: 0.50,
    ciHigh: 0.64,
    conviction: "MED",
    startTime: new Date(Date.now() + 1 * 60 * 60 * 1000 + 44 * 60 * 1000),
    qualified: true,
  },
  {
    id: "4",
    game: "BOS @ TB",
    gameTime: "6:10 PM ET",
    market: "Home ML",
    marketType: "moneyline",
    modelProb: 51.2,
    bovadaProb: 49.8,
    ciLow: 0.45,
    ciHigh: 0.57,
    conviction: "LOW",
    startTime: new Date(Date.now() + 1 * 60 * 60 * 1000 + 14 * 60 * 1000),
    qualified: false,
  },
  {
    id: "5",
    game: "CHI @ MIL",
    gameTime: "7:40 PM ET",
    market: "Totals Over 7.5",
    marketType: "totals",
    modelProb: 52.8,
    bovadaProb: 51.2,
    ciLow: 0.46,
    ciHigh: 0.59,
    conviction: "LOW",
    startTime: new Date(Date.now() + 2 * 60 * 60 * 1000 + 44 * 60 * 1000),
    qualified: false,
  },
  {
    id: "6",
    game: "TEX @ SEA",
    gameTime: "10:10 PM ET",
    market: "Home ML",
    marketType: "moneyline",
    modelProb: 53.5,
    bovadaProb: 52.1,
    ciLow: 0.47,
    ciHigh: 0.60,
    conviction: "LOW",
    startTime: new Date(Date.now() + 5 * 60 * 60 * 1000 + 14 * 60 * 1000),
    qualified: false,
  },
  {
    id: "7",
    game: "CIN @ STL",
    gameTime: "7:15 PM ET",
    market: "Totals Under 8.5",
    marketType: "totals",
    modelProb: 50.9,
    bovadaProb: 50.2,
    ciLow: 0.44,
    ciHigh: 0.58,
    conviction: "LOW",
    startTime: new Date(Date.now() + 2 * 60 * 60 * 1000 + 19 * 60 * 1000),
    qualified: false,
  },
  {
    id: "8",
    game: "MIN @ CLE",
    gameTime: "6:10 PM ET",
    market: "Home ML",
    marketType: "moneyline",
    modelProb: 54.1,
    bovadaProb: 53.2,
    ciLow: 0.48,
    ciHigh: 0.60,
    conviction: "LOW",
    startTime: new Date(Date.now() + 1 * 60 * 60 * 1000 + 14 * 60 * 1000),
    qualified: false,
  },
]

function useCountdown(targetDate: Date) {
  const [timeLeft, setTimeLeft] = useState("")

  useEffect(() => {
    const calculateTimeLeft = () => {
      const diff = targetDate.getTime() - Date.now()
      if (diff <= 0) return "Live"

      const hours = Math.floor(diff / (1000 * 60 * 60))
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))

      if (hours > 0) {
        return `${hours}h ${minutes}m`
      }
      return `${minutes}m`
    }

    setTimeLeft(calculateTimeLeft())
    const timer = setInterval(() => {
      setTimeLeft(calculateTimeLeft())
    }, 60000)

    return () => clearInterval(timer)
  }, [targetDate])

  return timeLeft
}

function CountdownCell({ startTime }: { startTime: Date }) {
  const timeLeft = useCountdown(startTime)
  return (
    <span 
      className="text-muted-foreground font-mono text-sm inline-flex items-center gap-1.5"
      title="Time until first pitch"
    >
      <Clock className="h-[11px] w-[11px] text-gray-400" />
      {timeLeft}
    </span>
  )
}

function PickRow({ pick, showBorder = true }: { pick: Pick; showBorder?: boolean }) {
  const edge = pick.modelProb - pick.bovadaProb
  const isModelHigher = pick.modelProb > pick.bovadaProb

  const getBorderColor = () => {
    if (!showBorder || !pick.qualified) return ""
    if (pick.conviction === "HIGH") return "border-l-4 border-l-emerald-500"
    if (pick.conviction === "MED") return "border-l-4 border-l-amber-500"
    return ""
  }

  return (
    <TableRow
      className={cn(
        "group cursor-pointer hover:bg-gray-800/40 transition-colors",
        getBorderColor()
      )}
      onClick={() => {
        // Row click handler - can be extended for navigation or modal
        console.log("Clicked pick:", pick.id)
      }}
    >
      {/* Game - always visible */}
      <TableCell className="font-medium">
        <div className="flex flex-col gap-0.5">
          <span className="text-foreground">{pick.game}</span>
          <span className="text-xs text-muted-foreground">{pick.gameTime}</span>
        </div>
      </TableCell>

      {/* Market */}
      <TableCell>
        {(() => {
          const isOver = pick.market.includes("Over")
          const isUnder = pick.market.includes("Under")
          const isMoneyline = pick.marketType === "moneyline"

          return (
            <Badge
              variant="secondary"
              className={cn(
                "text-xs inline-flex items-center gap-1",
                isOver
                  ? "bg-blue-500/20 text-blue-400 border-blue-500/30"
                  : "bg-amber-500/20 text-amber-400 border-amber-500/30"
              )}
            >
              {isOver && <ArrowUp className="h-3 w-3" />}
              {isUnder && <ArrowDown className="h-3 w-3" />}
              {isMoneyline && <ArrowRight className="h-3 w-3" />}
              {pick.market}
            </Badge>
          )
        })()}
      </TableCell>

      {/* Model % - hidden on smallest screens */}
      <TableCell className="hidden sm:table-cell">
        <span
          className={cn(
            "font-mono text-sm font-medium",
            isModelHigher ? "text-emerald-400" : "text-muted-foreground"
          )}
        >
          {pick.modelProb.toFixed(1)}%
        </span>
      </TableCell>

      {/* Confidence Bar - hidden on small screens */}
      <TableCell className="hidden lg:table-cell">
        <CompactProbabilityBar
          ciLow={pick.ciLow}
          ciHigh={pick.ciHigh}
          modelProb={pick.modelProb / 100}
          marketProb={pick.bovadaProb / 100}
        />
      </TableCell>

      {/* Bovada % - hidden on smallest screens */}
      <TableCell className="hidden sm:table-cell">
        <span className="font-mono text-sm text-muted-foreground">
          {pick.bovadaProb.toFixed(1)}%
        </span>
      </TableCell>

      {/* Edge */}
      <TableCell>
        <span
          className={cn(
            "font-mono text-sm font-semibold",
            edge > 0 ? "text-emerald-400" : "text-red-400"
          )}
        >
          {edge > 0 ? "+" : ""}
          {edge.toFixed(1)}%
        </span>
      </TableCell>

      {/* Conviction */}
      <TableCell className="hidden md:table-cell">
        <Badge
          variant="outline"
          className={cn(
            "text-xs font-semibold",
            pick.conviction === "HIGH" &&
              "border-emerald-500/50 text-emerald-400 bg-emerald-500/10",
            pick.conviction === "MED" &&
              "border-amber-500/50 text-amber-400 bg-amber-500/10",
            pick.conviction === "LOW" &&
              "border-muted-foreground/50 text-muted-foreground bg-muted/50"
          )}
        >
          {pick.conviction}
        </Badge>
      </TableCell>

      {/* Time countdown */}
      <TableCell>
        <CountdownCell startTime={pick.startTime} />
      </TableCell>

      {/* Chevron - visible on hover */}
      <TableCell className="w-8 pr-4">
        <ChevronRight className="h-3.5 w-3.5 text-gray-500 opacity-0 group-hover:opacity-100 transition-opacity" />
      </TableCell>
    </TableRow>
  )
}

export function PicksTable() {
  const [isOpen, setIsOpen] = useState(false)

  const qualifiedPicks = mockPicks.filter((p) => p.qualified)
  const nonQualifiedPicks = mockPicks.filter((p) => !p.qualified)

  return (
    <div className="space-y-4">
      {/* Qualified Picks Table */}
      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">
                Game
              </TableHead>
              <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">
                Market
              </TableHead>
              <TableHead className="hidden sm:table-cell text-xs uppercase tracking-wider text-muted-foreground">
                Model
              </TableHead>
              <TableHead className="hidden lg:table-cell text-xs uppercase tracking-wider text-muted-foreground">
                <div className="flex flex-col gap-0.5">
                  <span className="inline-flex items-center gap-1">
                    Confidence
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Info className="h-3 w-3 text-gray-400 cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent className="max-w-[280px] text-xs">
                        <p>{"The green bar shows the model's 80% credible interval. The white line is the model probability. The orange marker is Bovada's implied probability. When the entire green bar is to the right of the orange marker, this is a high-conviction pick."}</p>
                      </TooltipContent>
                    </Tooltip>
                  </span>
                  <span className="text-[9px] text-gray-500 font-normal normal-case tracking-normal">
                    | white line = Model {"  "} <span className="text-amber-500">◆</span> orange = Market
                  </span>
                </div>
              </TableHead>
              <TableHead className="hidden sm:table-cell text-xs uppercase tracking-wider text-muted-foreground">
                Bovada
              </TableHead>
              <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">
                Edge
              </TableHead>
              <TableHead className="hidden md:table-cell text-xs uppercase tracking-wider text-muted-foreground">
                Conviction
              </TableHead>
              <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">
                Time
              </TableHead>
              <TableHead className="w-8" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {qualifiedPicks.map((pick) => (
              <PickRow key={pick.id} pick={pick} showBorder={true} />
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Non-qualified Picks - Collapsible */}
      {nonQualifiedPicks.length > 0 && (
        <Collapsible open={isOpen} onOpenChange={setIsOpen}>
          <CollapsibleTrigger className="flex w-full items-center justify-between rounded-lg border bg-card/50 px-4 py-3 text-sm text-muted-foreground hover:bg-card transition-colors">
            <span>
              {nonQualifiedPicks.length} other games (below threshold)
            </span>
            <ChevronDown
              className={cn(
                "h-4 w-4 transition-transform duration-200",
                isOpen && "rotate-180"
              )}
            />
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2">
            <div className="rounded-lg border bg-card/50">
              <Table>
                <TableBody>
                  {nonQualifiedPicks.map((pick) => (
                    <PickRow key={pick.id} pick={pick} showBorder={false} />
                  ))}
                </TableBody>
              </Table>
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  )
}
