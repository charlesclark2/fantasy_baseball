"use client"

// E9.42 — "Log this prop": a bookkeeping affordance that copies the line the user is
// viewing on a projection page into their own Bet Log. This is NOT betting advice and
// carries NO recommendation: E5.4 found no demonstrable gain on this prop, so there is no
// +/- framing here — the user self-reports their line/stake/odds and we optionally store
// our projection alongside, clearly labelled as our projection at log time. The honest-
// framing scan (test_k_projection_serving.py) guards this file for banned language.
//
// E5.10 — generalized from pitcher-strikeouts-only to any prop kind, so the batter TOTAL
// BASES page gets the same one-click affordance the K page has had. The market strings and
// labels come from lib/prop-markets (shared with the manual "Log a prop" dialog) — two
// surfaces posting bets from independent market tables is how one of them ends up emitting
// a string settlement cannot grade, which sits Pending forever with no error (E9.49).

import { useMemo, useState } from "react"
import Link from "next/link"
import { CheckCircle, ClipboardList } from "lucide-react"
import { useMutation } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog"
import { apiFetch } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { PROP_MARKETS, bookLabel, type PropKind } from "@/lib/prop-markets"

/** The projection fields this affordance needs, normalized across prop kinds. Both the K and
 *  TB payloads are adapted to this at the call site, so the id-field difference
 *  (`pitcher_id` vs `batter_id`) never leaks in here. */
export interface LoggableProp {
  player_id: number
  full_name: string | null
  team: string | null
  opponent: string | null
  game_pk: number | null
  game_date: string | null
  primary_line: number | null
  book_comparisons: { book: string; line: number; over_odds: number | null; under_odds: number | null }[]
  /** OUR projected mean at log time — stored for the user's own reference only. */
  projection_mean: number | null
}

export function LogPropButton({ prop, kind }: { prop: LoggableProp; kind: PropKind }) {
  const cfg = PROP_MARKETS[kind]
  const projection = prop
  const { accessToken } = useAuth()
  const [open, setOpen] = useState(false)
  const [saved, setSaved] = useState(false)

  const books = projection.book_comparisons ?? []
  const canLog = projection.game_pk != null && (books.length > 0 || projection.primary_line != null)

  // Default to the book carrying the primary (consensus) line, else the first book.
  const defaultBook =
    books.find((b) => b.line === projection.primary_line)?.book ?? books[0]?.book ?? ""

  const [side, setSide] = useState<"over" | "under">("over")
  const [book, setBook] = useState(defaultBook)
  const [line, setLine] = useState<string>(
    projection.primary_line != null ? String(projection.primary_line) : "",
  )
  const [odds, setOdds] = useState<string>("")
  const [stake, setStake] = useState<string>("")
  const [notes, setNotes] = useState<string>("")

  const selectedBook = useMemo(() => books.find((b) => b.book === book), [books, book])

  // When the user changes book or side, sync the line + posted price from that book row.
  function syncFromBook(nextBook: string, nextSide: "over" | "under") {
    const row = books.find((b) => b.book === nextBook)
    if (row) {
      setLine(String(row.line))
      const posted = nextSide === "over" ? row.over_odds : row.under_odds
      setOdds(posted != null ? String(posted) : "")
    }
  }

  const mutation = useMutation({
    mutationFn: (body: object) =>
      apiFetch("/bets", { method: "POST", body: JSON.stringify(body) }, accessToken),
    onSuccess: () => setSaved(true),
  })

  function handleSave() {
    if (projection.game_pk == null || !line || !odds || !stake) return
    const opponent = projection.opponent ? ` vs ${projection.opponent}` : ""
    mutation.mutate({
      game_pk: projection.game_pk,
      score_date: projection.game_date ?? "",
      matchup: `${projection.full_name ?? cfg.playerLabel} ${cfg.matchupTag}${opponent}`,
      market: side === "over" ? cfg.marketOver : cfg.marketUnder,
      bookmaker: bookLabel(book || (selectedBook?.book ?? "")),
      american_odds: Number(odds),
      stake: Number(stake),
      prop_line: Number(line),
      player_id: projection.player_id,
      player_name: projection.full_name ?? undefined,
      projection: projection.projection_mean ?? undefined,
      ...(notes ? { notes } : {}),
    })
  }

  if (!canLog) return null

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o)
        if (o) {
          // Reset to a clean, book-synced state each time the tracker dialog opens.
          setSaved(false)
          mutation.reset()
          setBook(defaultBook)
          syncFromBook(defaultBook, side)
        }
      }}
    >
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="border-[#262626] bg-[#0d0d0d] text-xs text-gray-300 hover:bg-[#1a1a1a] hover:text-white"
        >
          <ClipboardList className="mr-1.5 h-3.5 w-3.5" />
          Log this prop
        </Button>
      </DialogTrigger>

      <DialogContent className="border-[#262626] bg-[#141414] text-white sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-white">Track this line</DialogTitle>
          <p className="text-xs text-gray-500">
            {projection.full_name ?? cfg.playerLabel}
            {projection.team ? ` · ${projection.team}` : ""}
            {projection.opponent ? ` vs ${projection.opponent}` : ""} · {cfg.lineLabel.toLowerCase()}
          </p>
        </DialogHeader>

        {saved ? (
          <div className="flex flex-col items-center gap-3 py-6 text-center">
            <CheckCircle className="h-8 w-8 text-emerald-400" />
            <p className="text-sm text-gray-300">Added to your Bet Log.</p>
            <Link href="/bet-log" className="text-xs text-emerald-400 underline hover:text-emerald-300">
              View Bet Log
            </Link>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4 py-2">
              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">Side</Label>
                <Select
                  value={side}
                  onValueChange={(v) => {
                    const s = v as "over" | "under"
                    setSide(s)
                    syncFromBook(book, s)
                  }}
                >
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
                <Label className="text-xs text-gray-400">Book</Label>
                {books.length > 0 ? (
                  <Select
                    value={book}
                    onValueChange={(v) => {
                      setBook(v)
                      syncFromBook(v, side)
                    }}
                  >
                    <SelectTrigger className="border-[#262626] bg-[#0a0a0a] text-sm text-white">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="border-[#262626] bg-[#141414]">
                      {books.map((b, i) => (
                        <SelectItem key={`${b.book}-${i}`} value={b.book}
                          className="text-sm text-white capitalize focus:bg-[#1e1e1e] focus:text-white">
                          {bookLabel(b.book)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input value={book} onChange={(e) => setBook(e.target.value)}
                    placeholder="Book" className="border-[#262626] bg-[#0a0a0a] text-sm text-white placeholder:text-gray-600" />
                )}
              </div>

              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">{cfg.lineLabel}</Label>
                <Input type="number" step="0.5" value={line} onChange={(e) => setLine(e.target.value)}
                  placeholder="6.5" className="border-[#262626] bg-[#0a0a0a] text-sm text-white placeholder:text-gray-600" />
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

              <div className="flex flex-col gap-1.5">
                <Label className="text-xs text-gray-400">Notes (optional)</Label>
                <Input value={notes} onChange={(e) => setNotes(e.target.value)}
                  placeholder="Context…" className="border-[#262626] bg-[#0a0a0a] text-sm text-white placeholder:text-gray-600" />
              </div>
            </div>

            {projection.projection_mean != null && (
              <p className="text-[11px] text-gray-500">
                Our projection at log time: {projection.projection_mean.toFixed(1)}{" "}
                {cfg.matchupTag} (stored for your reference only).
              </p>
            )}
            <p className="text-[11px] leading-relaxed text-gray-600">
              Bookkeeping only — this copies the line you entered into your log so you can track it.
              It is not betting advice and makes no profitability claim.
            </p>

            {mutation.isError && (
              <p className="text-xs text-[#ef4444]">Could not save — please try again.</p>
            )}

            <DialogFooter className="gap-2">
              <Button variant="ghost" onClick={() => setOpen(false)}
                className="text-gray-400 hover:bg-[#1a1a1a] hover:text-white">Cancel</Button>
              <Button
                onClick={handleSave}
                disabled={!line || !odds || !stake || mutation.isPending}
                className="bg-emerald-500 font-semibold text-[#0a0a0a] hover:bg-emerald-600"
              >
                {mutation.isPending ? "Saving…" : "Add to Bet Log"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
