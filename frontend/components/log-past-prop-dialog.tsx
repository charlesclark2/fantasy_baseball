"use client"

// E9.42 — "Log a prop" (manual entry). Lets a user back-log a strikeout prop they placed on
// any game within the last ~14 days, straight into their Bet Log, even when we never generated
// a projection for that start. Pure bookkeeping: the user self-reports side / line / book / odds
// / stake and it settles later against the pitcher's actual strikeouts. NOT betting advice and
// carries no recommendation (E5.4 found no demonstrable gain on this prop) — the honest-framing
// scan (test_k_projection_serving.py) guards this file for banned language.

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

const BOOKMAKER_OPTIONS = ["Bovada", "DraftKings", "FanDuel", "BetMGM", "Pinnacle", "Other"]

interface Starter {
  game_pk: number
  pitcher_id: number
  pitcher_name: string
  team: string | null
  opponent: string | null
  game_date: string
}

interface StartersResponse {
  date: string
  starters: Starter[]
}

export function LogPastPropDialog() {
  const { accessToken } = useAuth()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [saved, setSaved] = useState(false)

  const [date, setDate] = useState<Date>(() => new Date())
  const [calOpen, setCalOpen] = useState(false)
  const dateStr = format(date, "yyyy-MM-dd")

  const [pitcherId, setPitcherId] = useState<string>("")
  const [side, setSide] = useState<"over" | "under">("over")
  const [book, setBook] = useState("Bovada")
  const [line, setLine] = useState("")
  const [odds, setOdds] = useState("")
  const [stake, setStake] = useState("")
  const [notes, setNotes] = useState("")

  // Starting pitchers for the chosen date (both starters per game). Settlement keys off the
  // pitcher_id + game_pk this returns, so the user picks a real start rather than free-typing.
  const { data, isLoading } = useQuery<StartersResponse>({
    queryKey: ["prop-starters", dateStr],
    queryFn: () => apiFetch(`/props/starters?date=${dateStr}`, {}, accessToken),
    enabled: !!accessToken && open,
    staleTime: 5 * 60 * 1000,
  })

  const starters = data?.starters ?? []
  const selected = useMemo(
    () => starters.find((s) => String(s.pitcher_id) === pitcherId),
    [starters, pitcherId],
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
    const opponent = selected.opponent ? ` vs ${selected.opponent}` : ""
    mutation.mutate({
      game_pk: selected.game_pk,
      score_date: selected.game_date,
      matchup: `${selected.pitcher_name} K${opponent}`,
      market: side === "over" ? "strikeouts over" : "strikeouts under",
      bookmaker: book,
      american_odds: Number(odds),
      stake: Number(stake),
      prop_line: Number(line),
      player_id: selected.pitcher_id,
      player_name: selected.pitcher_name,
      ...(notes ? { notes } : {}),
    })
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o)
        if (o) reset()
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
          <DialogTitle className="text-white">Log a strikeout prop</DialogTitle>
          <p className="text-xs text-gray-500">
            Record a pitcher-strikeout prop you placed — it settles against the pitcher&apos;s actual
            strikeouts once the game is final.
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

              {/* Pitcher */}
              <div className="col-span-2 flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">Pitcher</Label>
                <Select value={pitcherId} onValueChange={setPitcherId} disabled={isLoading || starters.length === 0}>
                  <SelectTrigger className="border-[#262626] bg-[#0a0a0a] text-sm text-white">
                    <SelectValue placeholder={
                      isLoading ? "Loading starters…" : starters.length === 0 ? "No starters for this date yet" : "Select pitcher…"
                    } />
                  </SelectTrigger>
                  <SelectContent className="border-[#262626] bg-[#141414]">
                    {starters.map((s) => (
                      <SelectItem key={`${s.game_pk}-${s.pitcher_id}`} value={String(s.pitcher_id)}
                        className="text-sm text-white focus:bg-[#1e1e1e] focus:text-white">
                        {s.pitcher_name}{s.team ? ` (${s.team}${s.opponent ? ` vs ${s.opponent}` : ""})` : ""}
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
                <Label className="text-xs text-gray-400">Strikeout line</Label>
                <Input type="number" step="0.5" value={line} onChange={(e) => setLine(e.target.value)}
                  placeholder="6.5" className="border-[#262626] bg-[#0a0a0a] text-sm text-white placeholder:text-gray-600" />
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
