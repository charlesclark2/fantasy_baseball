"use client"

// E9.42 — "Log a prop" (manual entry). Lets a user back-log a prop they placed on any game
// within the last ~14 days, straight into their Bet Log, even when we never generated a
// projection for that start. Pure bookkeeping: the user self-reports side / line / book / odds
// / stake and it settles later against the player's actual total. NOT betting advice and
// carries no recommendation (E5.4 found no demonstrable gain on this prop) — the honest-framing
// scan (test_k_projection_serving.py) guards this file for banned language.
//
// E5.10 — extended to BATTER TOTAL BASES. /props shipped a Total Bases tab (E5.9) while this
// dialog and settlement were both strikeout-only, so a TB prop the user had actually placed
// could not be recorded at all. The prop type drives three things together — which picker the
// dialog loads (starters vs batters), the `market` string it posts, and therefore which actual
// settlement grades it against — so they are derived from ONE table below rather than three
// parallel ternaries that could drift apart.

import { useMemo, useState } from "react"
import { format, subDays } from "date-fns"
import { CalendarIcon, CheckCircle, ClipboardList } from "lucide-react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog"
import { apiFetch } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { normalizeTeam } from "@/lib/teams"

const BOOKMAKER_OPTIONS = ["Bovada", "DraftKings", "FanDuel", "BetMGM", "Pinnacle", "Other"]

// One row per prop type: the picker endpoint, the posted `market` strings, and the labels.
// Settlement keys off `market` (settle_user_bets.py `_K_PROP_MARKETS` / `_TB_PROP_MARKETS`),
// so a market string here that settlement does not know would sit Pending forever — the E9.49
// unsettleable-bet class. Keep the two in sync.
const PROP_TYPES = {
  strikeouts: {
    label: "Pitcher strikeouts",
    endpoint: "/props/starters",
    collection: "starters",
    queryKey: "prop-starters",
    playerLabel: "Pitcher",
    lineLabel: "Strikeout line",
    linePlaceholder: "6.5",
    matchupTag: "K",
    marketOver: "strikeouts over",
    marketUnder: "strikeouts under",
    settlesAgainst: "the pitcher's actual strikeouts",
    emptyLabel: "No starters for this date yet",
  },
  total_bases: {
    label: "Batter total bases",
    endpoint: "/props/batters",
    collection: "batters",
    queryKey: "prop-batters",
    playerLabel: "Batter",
    lineLabel: "Total bases line",
    linePlaceholder: "1.5",
    matchupTag: "TB",
    marketOver: "total bases over",
    marketUnder: "total bases under",
    settlesAgainst: "the batter's actual total bases",
    emptyLabel: "No posted lineups for this date yet",
  },
} as const

type PropType = keyof typeof PROP_TYPES

// Both pickers are normalized to this shape on read, so the rest of the dialog never branches
// on prop type again (the /props/starters rows key their id as `pitcher_id`, the batters rows
// as `player_id` — a difference that must not leak past this boundary).
interface PropPlayer {
  game_pk: number
  player_id: number
  player_name: string
  team: string | null
  opponent: string | null
  game_date: string
}

export function LogPastPropDialog({ initialDate }: { initialDate?: Date }) {
  const { accessToken } = useAuth()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [saved, setSaved] = useState(false)

  // Clamp the seed date into the [today-14, today] window this dialog supports, so a Props page
  // opened on an out-of-window date still starts somewhere valid.
  const clampToWindow = (d: Date) => {
    const today = new Date()
    const floor = subDays(today, 14)
    if (d > today) return today
    if (d < floor) return floor
    return d
  }
  const [date, setDate] = useState<Date>(() => clampToWindow(initialDate ?? new Date()))
  const [calOpen, setCalOpen] = useState(false)
  const dateStr = format(date, "yyyy-MM-dd")

  const [propType, setPropType] = useState<PropType>("strikeouts")
  const cfg = PROP_TYPES[propType]
  const [pitcherId, setPitcherId] = useState<string>("")
  const [side, setSide] = useState<"over" | "under">("over")
  const [book, setBook] = useState("Bovada")
  const [line, setLine] = useState("")
  const [odds, setOdds] = useState("")
  const [stake, setStake] = useState("")
  const [notes, setNotes] = useState("")

  // The eligible players for the chosen date + prop type: starting pitchers, or every batter
  // in a posted lineup. Settlement keys off the player_id + game_pk this returns, so the user
  // picks a real appearance rather than free-typing.
  const { data, isLoading } = useQuery<Record<string, unknown>>({
    queryKey: [cfg.queryKey, dateStr],
    queryFn: () => apiFetch(`${cfg.endpoint}?date=${dateStr}`, {}, accessToken),
    enabled: !!accessToken && open,
    staleTime: 5 * 60 * 1000,
  })

  // Normalize both response shapes to PropPlayer. `?? []` on a missing collection is the
  // NF-C0 guard: an older deployed API answering without the key must fall through to a
  // visible empty state, never render nothing.
  const players: PropPlayer[] = useMemo(() => {
    const raw = (data?.[cfg.collection] as Record<string, unknown>[] | undefined) ?? []
    return raw
      .map((r) => ({
        game_pk: Number(r.game_pk),
        player_id: Number(r.player_id ?? r.pitcher_id),
        player_name: String(r.player_name ?? r.pitcher_name ?? ""),
        team: (r.team as string | null) ?? null,
        opponent: (r.opponent as string | null) ?? null,
        game_date: String(r.game_date ?? dateStr),
      }))
      .filter((p) => Number.isFinite(p.player_id) && p.player_name)
  }, [data, cfg.collection, dateStr])

  const selected = useMemo(
    () => players.find((s) => String(s.player_id) === pitcherId),
    [players, pitcherId],
  )

  const mutation = useMutation({
    mutationFn: (body: object) =>
      apiFetch("/bets", { method: "POST", body: JSON.stringify(body) }, accessToken),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bets"] })
      setSaved(true)
    },
  })

  function reset() {
    setSaved(false)
    mutation.reset()
    setPropType("strikeouts")
    setPitcherId("")
    setSide("over")
    setBook("Bovada")
    setLine("")
    setOdds("")
    setStake("")
    setNotes("")
  }

  function handleSave() {
    if (!selected || !line || !odds || !stake) return
    const opponent = selected.opponent ? ` vs ${normalizeTeam(selected.opponent)}` : ""
    mutation.mutate({
      game_pk: selected.game_pk,
      score_date: selected.game_date,
      matchup: `${selected.player_name} ${cfg.matchupTag}${opponent}`,
      market: side === "over" ? cfg.marketOver : cfg.marketUnder,
      bookmaker: book,
      american_odds: Number(odds),
      stake: Number(stake),
      prop_line: Number(line),
      player_id: selected.player_id,
      player_name: selected.player_name,
      ...(notes ? { notes } : {}),
    })
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o)
        if (o) {
          setDate(clampToWindow(initialDate ?? new Date()))
          reset()
        }
      }}
    >
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="border-[#262626] bg-[#0a0a0a] text-xs text-gray-300 hover:bg-[#1a1a1a] hover:text-white"
        >
          <ClipboardList className="mr-1.5 h-3.5 w-3.5" />
          Log a prop
        </Button>
      </DialogTrigger>

      <DialogContent className="border-[#262626] bg-[#141414] text-white sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-white">Log a prop</DialogTitle>
          <p className="text-xs text-gray-500">
            Record a prop you placed — it settles against {cfg.settlesAgainst} once the game is
            final.
          </p>
        </DialogHeader>

        {saved ? (
          <div className="flex flex-col items-center gap-3 py-6 text-center">
            <CheckCircle className="h-8 w-8 text-emerald-400" />
            <p className="text-sm text-gray-300">Added to your Bet Log.</p>
            <button onClick={reset} className="text-xs text-emerald-400 underline hover:text-emerald-300">
              Log another
            </button>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4 py-2">
              {/* Prop type — drives the picker, the line label AND the posted market string */}
              <div className="col-span-2 flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">Prop</Label>
                <Select
                  value={propType}
                  onValueChange={(v) => { setPropType(v as PropType); setPitcherId(""); setLine("") }}
                >
                  <SelectTrigger
                    aria-label="Prop type"
                    data-testid="log-prop-type"
                    className="border-[#262626] bg-[#0a0a0a] text-sm text-white"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="border-[#262626] bg-[#141414]">
                    {(Object.keys(PROP_TYPES) as PropType[]).map((k) => (
                      <SelectItem key={k} value={k}
                        className="text-sm text-white focus:bg-[#1e1e1e] focus:text-white">
                        {PROP_TYPES[k].label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Date (last 14 days) */}
              <div className="col-span-2 flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">Game date</Label>
                <Popover open={calOpen} onOpenChange={setCalOpen}>
                  <PopoverTrigger asChild>
                    <Button variant="outline"
                      className="w-full justify-start border-[#262626] bg-[#0a0a0a] text-sm text-white hover:bg-[#1a1a1a] hover:text-white">
                      <CalendarIcon className="mr-2 h-4 w-4 text-gray-500" />
                      {format(date, "MMM d, yyyy")}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto border-[#262626] bg-[#141414] p-0">
                    <Calendar mode="single" selected={date}
                      onSelect={(d) => { if (d) { setDate(d); setCalOpen(false); setPitcherId("") } }}
                      fromDate={subDays(new Date(), 14)} toDate={new Date()} initialFocus />
                  </PopoverContent>
                </Popover>
              </div>

              {/* Player (starting pitcher, or a batter in a posted lineup) */}
              <div className="col-span-2 flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">{cfg.playerLabel}</Label>
                <Select value={pitcherId} onValueChange={setPitcherId} disabled={isLoading || players.length === 0}>
                  <SelectTrigger data-testid="log-prop-player"
                    className="border-[#262626] bg-[#0a0a0a] text-sm text-white">
                    <SelectValue placeholder={
                      isLoading ? "Loading…" : players.length === 0 ? cfg.emptyLabel
                        : `Select ${cfg.playerLabel.toLowerCase()}…`
                    } />
                  </SelectTrigger>
                  <SelectContent className="border-[#262626] bg-[#141414]">
                    {players.map((s) => (
                      <SelectItem key={`${s.game_pk}-${s.player_id}`} value={String(s.player_id)}
                        className="text-sm text-white focus:bg-[#1e1e1e] focus:text-white">
                        {s.player_name}
                        {s.team ? ` (${normalizeTeam(s.team)}${s.opponent ? ` vs ${normalizeTeam(s.opponent)}` : ""})` : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">Side</Label>
                <Select value={side} onValueChange={(v) => setSide(v as "over" | "under")}>
                  <SelectTrigger className="border-[#262626] bg-[#0a0a0a] text-sm text-white">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="border-[#262626] bg-[#141414]">
                    <SelectItem value="over" className="text-sm text-white focus:bg-[#1e1e1e] focus:text-white">Over</SelectItem>
                    <SelectItem value="under" className="text-sm text-white focus:bg-[#1e1e1e] focus:text-white">Under</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">{cfg.lineLabel}</Label>
                <Input type="number" step="0.5" value={line} onChange={(e) => setLine(e.target.value)}
                  data-testid="log-prop-line"
                  placeholder={cfg.linePlaceholder}
                  className="border-[#262626] bg-[#0a0a0a] text-sm text-white placeholder:text-gray-600" />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">Book</Label>
                <Select value={book} onValueChange={setBook}>
                  <SelectTrigger className="border-[#262626] bg-[#0a0a0a] text-sm text-white">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="border-[#262626] bg-[#141414]">
                    {BOOKMAKER_OPTIONS.map((b) => (
                      <SelectItem key={b} value={b} className="text-sm text-white focus:bg-[#1e1e1e] focus:text-white">{b}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">Odds (American)</Label>
                <Input type="number" value={odds} onChange={(e) => setOdds(e.target.value)}
                  placeholder="-115" className="border-[#262626] bg-[#0a0a0a] text-sm text-white placeholder:text-gray-600" />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">Stake ($)</Label>
                <Input type="number" step="any" min={0.01} value={stake} onChange={(e) => setStake(e.target.value)}
                  placeholder="50" className="border-[#262626] bg-[#0a0a0a] text-sm text-white placeholder:text-gray-600" />
              </div>

              <div className="col-span-2 flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">Notes (optional)</Label>
                <Input value={notes} onChange={(e) => setNotes(e.target.value)}
                  placeholder="Context…" className="border-[#262626] bg-[#0a0a0a] text-sm text-white placeholder:text-gray-600" />
              </div>
            </div>

            <p className="text-[11px] leading-relaxed text-gray-600">
              Bookkeeping only — this records the prop you entered so you can track it. It is not
              betting advice and makes no profitability claim.
            </p>

            {mutation.isError && (
              <p className="text-xs text-[#ef4444]">Could not save — please try again.</p>
            )}

            <DialogFooter className="gap-2">
              <Button variant="ghost" onClick={() => setOpen(false)}
                className="text-gray-400 hover:bg-[#1a1a1a] hover:text-white">Cancel</Button>
              <Button onClick={handleSave}
                disabled={!selected || !line || !odds || !stake || mutation.isPending}
                className="bg-emerald-500 font-semibold text-[#0a0a0a] hover:bg-emerald-600">
                {mutation.isPending ? "Saving…" : "Add to Bet Log"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
