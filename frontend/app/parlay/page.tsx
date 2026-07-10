"use client"

// ---------------------------------------------------------------------------
// Parlay decision-support CALCULATOR — Story E10.1 (honest MVP).
//
// Build a parlay and see the TRUTH about it: our model's true combined probability (same-game legs
// correlation-adjusted, never the naive product) vs the book's implied probability from the parlay
// price, the expected value, and a plain-language verdict. A transparency/education tool — NOT a bet
// recommendation (E10.3 is the recommender, hard-gated behind a proven advantage we do not have;
// best_alpha=0 holds).
//
// Pick the book you're betting with → each leg auto-fills that book's latest line + odds, and shows
// the model's probability next to the book's no-vig probability. Honest framing: no promotional /
// bet-recommendation wording anywhere on this surface; the "most parlays are negative expected value
// after vig" disclaimer is always shown. Guarded by test_parlay_serving.py. Per-leg model
// probabilities + per-book odds come from the SERVING CACHE via the stateless /parlay endpoints.
// ---------------------------------------------------------------------------

import { useEffect, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { format } from "date-fns"
import { CalendarIcon, Info, Plus, X, Trash2 } from "lucide-react"
import { Nav } from "@/components/nav"
import { AuthGuard } from "@/components/auth-guard"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { useAuth } from "@/lib/auth-context"
import { useSelectedDate } from "@/lib/date-context"
import { apiFetch } from "@/lib/api"

// ---------------------------------------------------------------------------
// Types — mirror app/backend/routers/parlay.py
// ---------------------------------------------------------------------------

interface BookOdds {
  american: number | null
  book_devig_prob: number | null
  model_prob: number | null
  line: number | null
}
interface LegSide {
  side: string
  team?: string | null
  model_prob: number // consensus model prob (fallback when a book has no line)
  books: Record<string, BookOdds>
}
interface Market {
  market_type: "h2h" | "totals" | "strikeouts"
  label: string
  line?: number | null
  pitcher_id?: number | null
  pitcher_name?: string | null
  sides: LegSide[]
}
interface GameLegs {
  game_pk: number
  home_team: string | null
  away_team: string | null
  game_start_utc: string | null
  markets: Market[]
}
interface BookOption {
  book_key: string
  book_name: string
  is_sharp_reference: boolean
}
interface LegUniverse {
  date: string
  books: BookOption[]
  default_book_key: string | null
  games: GameLegs[]
  disclaimer?: string
}

interface SlipLeg {
  key: string
  game_pk: number
  market_type: "h2h" | "totals" | "strikeouts"
  side: string
  pitcher_id?: number | null
  label: string
  odds: string // user-editable American odds (auto-filled from the selected book)
}

interface EvalLeg {
  market_type: string
  side: string
  hit_prob: number | null
  book_implied_prob: number | null
  line: number | null
  resolved: boolean
  label?: string | null
}
interface CorrGroup {
  game_pk: number | null
  is_same_game: boolean
  correlation_source: string
}
interface EvalResult {
  legs: EvalLeg[]
  combined_true_prob: number | null
  naive_independent_prob: number | null
  correlation_groups: CorrGroup[]
  has_same_game: boolean
  parlay_decimal_odds: number | null
  parlay_price_source: string
  book_implied_prob: number | null
  expected_value_per_dollar: number | null
  verdict: string
  flags: string[]
  disclaimer: string
}

const DISCLAIMER_FALLBACK =
  "This is a decision-support calculator, not betting advice, and we make no profitability claim. " +
  "Most parlays are negative expected value once the sportsbook's vig is priced in."

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const pct = (p: number | null | undefined, d = 1) =>
  p == null ? "—" : `${(p * 100).toFixed(d)}%`

const fmtAmerican = (a: number | null | undefined) =>
  a == null ? "—" : `${a >= 0 ? "+" : ""}${a}`

function sideLabel(g: GameLegs, m: Market, s: LegSide, line: number | null): string {
  if (m.market_type === "h2h")
    return `${s.team ?? (s.side === "home" ? g.home_team : g.away_team) ?? s.side} to win`
  if (m.market_type === "totals")
    return `${s.side === "over" ? "Over" : "Under"}${line != null ? ` ${line}` : ""} runs`
  return `${m.pitcher_name ?? "Pitcher"} ${s.side === "over" ? "Over" : "Under"}${line != null ? ` ${line}` : ""} K`
}

function fmtGameTime(raw: string | null): string | null {
  if (!raw) return null
  const iso = raw.endsWith("Z") || /[+-]\d\d:?\d\d$/.test(raw) ? raw : raw + "Z"
  const d = new Date(iso)
  if (isNaN(d.getTime())) return null
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
}

// The view of a side at the selected book: model prob (book-line-specific when available), the book's
// no-vig prob, the posted line, and the American odds. Falls back to the consensus model prob.
function sideView(m: Market, s: LegSide, bookKey: string | null) {
  const bd = bookKey ? s.books[bookKey] : undefined
  return {
    modelProb: bd?.model_prob ?? s.model_prob,
    bookDevig: bd?.book_devig_prob ?? null,
    line: bd?.line ?? m.line ?? null,
    american: bd?.american ?? null,
  }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function ParlayPageInner() {
  const { accessToken, email } = useAuth()
  const { selectedDate, setSelectedDate, isoDate } = useSelectedDate()
  const [calOpen, setCalOpen] = useState(false)
  const [slip, setSlip] = useState<SlipLeg[]>([])
  const [parlayOdds, setParlayOdds] = useState<string>("")
  const [bookKey, setBookKey] = useState<string | null>(null)

  const { data: universe, isLoading, isError } = useQuery<LegUniverse>({
    queryKey: ["parlay-legs", isoDate],
    queryFn: () => apiFetch(`/parlay/legs?date=${isoDate}`, {}, accessToken!),
    enabled: !!accessToken,
    staleTime: 1000 * 60 * 10,
  })

  // Default the book selection to the slate's default (Bovada when present) once loaded.
  useEffect(() => {
    if (universe && bookKey == null) setBookKey(universe.default_book_key ?? universe.books[0]?.book_key ?? null)
  }, [universe, bookKey])

  const games = universe?.games ?? []

  // Index sides by (game_pk, market, side) so the slip can re-derive odds/line when the book changes.
  const sideIndex = useMemo(() => {
    const idx = new Map<string, { g: GameLegs; m: Market; s: LegSide }>()
    for (const g of games)
      for (const m of g.markets)
        for (const s of m.sides) idx.set(`${g.game_pk}:${m.market_type}:${s.side}`, { g, m, s })
    return idx
  }, [games])

  // American odds for a leg at the current book (string, "" when the book has no price for it).
  function bookOddsFor(leg: { game_pk: number; market_type: string; side: string }): string {
    const hit = sideIndex.get(`${leg.game_pk}:${leg.market_type}:${leg.side}`)
    if (!hit || !bookKey) return ""
    const a = hit.s.books[bookKey]?.american
    return a == null ? "" : String(a)
  }

  function toggleLeg(g: GameLegs, m: Market, s: LegSide) {
    const key = `${g.game_pk}:${m.market_type}:${s.side}`
    setSlip((prev) => {
      if (prev.some((l) => l.key === key)) return prev.filter((l) => l.key !== key)
      const line = sideView(m, s, bookKey).line
      const a = bookKey ? s.books[bookKey]?.american : null
      return [...prev, {
        key, game_pk: g.game_pk, market_type: m.market_type, side: s.side,
        pitcher_id: m.pitcher_id ?? null, label: sideLabel(g, m, s, line),
        odds: a == null ? "" : String(a),
      }]
    })
  }

  const removeLeg = (key: string) => setSlip((p) => p.filter((l) => l.key !== key))
  const setOdds = (key: string, odds: string) =>
    setSlip((p) => p.map((l) => (l.key === key ? { ...l, odds } : l)))
  const clearSlip = () => { setSlip([]); setParlayOdds("") }

  // Changing the book re-fills every leg's odds with that book's latest price (auto-populate).
  function changeBook(bk: string) {
    setBookKey(bk)
    setSlip((prev) => prev.map((l) => {
      const hit = sideIndex.get(`${l.game_pk}:${l.market_type}:${l.side}`)
      const a = hit?.s.books[bk]?.american
      const line = hit ? sideView(hit.m, hit.s, bk).line : null
      return {
        ...l,
        odds: a == null ? l.odds : String(a),
        label: hit ? sideLabel(hit.g, hit.m, hit.s, line) : l.label,
      }
    }))
  }

  const hasSameGame = useMemo(() => {
    const counts = new Map<number, number>()
    for (const l of slip) counts.set(l.game_pk, (counts.get(l.game_pk) ?? 0) + 1)
    return [...counts.values()].some((c) => c > 1)
  }, [slip])

  const evalBody = useMemo(() => {
    const legs = slip.map((l) => ({
      game_pk: l.game_pk, market_type: l.market_type, side: l.side, book_key: bookKey,
      book_odds_american: l.odds.trim() === "" ? null : Number(l.odds),
      pitcher_id: l.pitcher_id ?? null, label: l.label,
    }))
    const parlay = parlayOdds.trim() === "" ? null : Number(parlayOdds)
    return { legs, parlay_odds_american: Number.isFinite(parlay as number) ? parlay : null, date: isoDate }
  }, [slip, parlayOdds, isoDate, bookKey])

  const { data: result } = useQuery<EvalResult>({
    queryKey: ["parlay-eval", JSON.stringify(evalBody)],
    queryFn: () =>
      apiFetch(`/parlay/evaluate`, { method: "POST", body: JSON.stringify(evalBody) }, accessToken!),
    enabled: !!accessToken && slip.length > 0,
    staleTime: 0,
  })

  const bookName = universe?.books.find((b) => b.book_key === bookKey)?.book_name ?? bookKey ?? "book"

  return (
    <>
      <Nav authenticated activeLink="parlay" userEmail={email} />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <h1 className="mb-1 text-2xl font-bold text-white">Parlay Calculator</h1>
        <p className="mb-5 max-w-3xl text-sm text-gray-500">
          Build a parlay and see the truth about it — our model&apos;s estimate of its true combined
          probability next to the price the sportsbook is charging you, and the resulting expected
          value. Pick the book you&apos;re betting with and each leg fills in that book&apos;s latest
          line and odds. Same-game legs are correlation-adjusted, not naively multiplied. A transparency
          calculator, not a bet recommendation.
        </p>

        {/* Book + date controls */}
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <span className="text-[11px] uppercase tracking-wider text-gray-600">Book</span>
            <Select value={bookKey ?? undefined} onValueChange={changeBook}>
              <SelectTrigger className="h-9 w-[190px] border-[#262626] bg-[#141414] text-sm text-white">
                <SelectValue placeholder="Select a book" />
              </SelectTrigger>
              <SelectContent className="border-[#262626] bg-[#141414] text-white">
                {(universe?.books ?? []).map((b) => (
                  <SelectItem key={b.book_key} value={b.book_key}>
                    {b.book_name}{b.is_sharp_reference ? " (sharp ref.)" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Popover open={calOpen} onOpenChange={setCalOpen}>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                className="h-9 w-[156px] justify-start gap-2 border-[#262626] bg-[#141414] text-left text-sm font-normal text-white hover:bg-[#1a1a1a]"
              >
                <CalendarIcon className="h-4 w-4 text-gray-500" />
                {format(selectedDate, "MMM d, yyyy")}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto border-[#262626] bg-[#141414] p-0" align="end">
              <Calendar
                mode="single"
                selected={selectedDate}
                onSelect={(d) => { if (d) { setSelectedDate(d); setCalOpen(false) } }}
                initialFocus
              />
            </PopoverContent>
          </Popover>
        </div>

        <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
          {/* ── Leg picker ────────────────────────────────────────────── */}
          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-400">Add legs</h2>
            {isLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28 w-full rounded-lg" />)}
              </div>
            ) : isError ? (
              <div className="rounded-lg border border-[#262626] bg-[#111111] px-4 py-8 text-center text-sm text-gray-500">
                Couldn&apos;t load the slate right now. Please try again shortly.
              </div>
            ) : games.length === 0 ? (
              <div className="rounded-lg border border-[#262626] bg-[#111111] px-4 py-10 text-center">
                <p className="text-sm text-gray-400">No model probabilities available for {format(selectedDate, "MMM d, yyyy")} yet.</p>
                <p className="mt-1 text-xs text-gray-600">Legs appear once the model posts probabilities for the day&apos;s slate. Try another date.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {games.map((g) => (
                  <div key={g.game_pk} className="rounded-lg border border-[#262626] bg-[#111111] p-4">
                    <div className="mb-2 flex items-center justify-between">
                      <div className="text-sm font-semibold text-white">
                        {g.away_team ?? "Away"} @ {g.home_team ?? "Home"}
                      </div>
                      {fmtGameTime(g.game_start_utc) && (
                        <div className="text-[11px] text-gray-500">{fmtGameTime(g.game_start_utc)}</div>
                      )}
                    </div>
                    <div className="space-y-2.5">
                      {g.markets.map((m, mi) => (
                        <div key={mi}>
                          <div className="mb-1 text-[10px] uppercase tracking-wider text-gray-600">{m.label}</div>
                          <div className="flex flex-wrap gap-2">
                            {m.sides.map((s) => {
                              const key = `${g.game_pk}:${m.market_type}:${s.side}`
                              const active = slip.some((l) => l.key === key)
                              const v = sideView(m, s, bookKey)
                              return (
                                <button
                                  key={s.side}
                                  onClick={() => toggleLeg(g, m, s)}
                                  className={`flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors ${
                                    active
                                      ? "border-sky-500 bg-sky-500/10 text-sky-200"
                                      : "border-[#262626] bg-[#141414] text-gray-300 hover:border-[#3a3a3a]"
                                  }`}
                                >
                                  {active ? <X className="h-3 w-3" /> : <Plus className="h-3 w-3" />}
                                  <span>{sideLabel(g, m, s, v.line)}</span>
                                  <span className="tabular-nums text-emerald-400/90" title="Model probability">{pct(v.modelProb, 0)}</span>
                                  {v.american != null && (
                                    <span className="tabular-nums text-gray-500" title={`${bookName} odds`}>{fmtAmerican(v.american)}</span>
                                  )}
                                </button>
                              )
                            })}
                          </div>
                          {m.market_type === "strikeouts" && (
                            <p className="mt-1 text-[10px] text-gray-600">Enter your book&apos;s K odds in the slip — strikeout lines vary by book.</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* ── Slip + result ─────────────────────────────────────────── */}
          <section className="lg:sticky lg:top-4 lg:self-start">
            <div className="rounded-lg border border-[#262626] bg-[#111111] p-4">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-400">Your parlay ({slip.length})</h2>
                {slip.length > 0 && (
                  <button onClick={clearSlip} className="flex items-center gap-1 text-[11px] text-gray-500 hover:text-gray-300">
                    <Trash2 className="h-3 w-3" /> Clear
                  </button>
                )}
              </div>

              {slip.length === 0 ? (
                <p className="py-6 text-center text-xs text-gray-600">
                  Pick legs on the left to build your parlay. Odds fill in from your selected book — adjust
                  any leg&apos;s odds to match what you&apos;re actually taking.
                </p>
              ) : (
                <div className="space-y-2.5">
                  {slip.map((l) => {
                    const hit = sideIndex.get(l.key)
                    const v = hit ? sideView(hit.m, hit.s, bookKey) : null
                    return (
                      <div key={l.key} className="rounded-md border border-[#1e1e1e] bg-[#0d0d0d] p-2.5">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0 text-xs font-medium text-gray-200">{l.label}</div>
                          <button onClick={() => removeLeg(l.key)} className="text-gray-600 hover:text-gray-300" aria-label="Remove leg">
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </div>
                        {/* Model vs book (no-vig) — a factual transparency comparison, not a bet-rec claim. */}
                        <div className="mt-1 flex items-center gap-3 text-[10px]">
                          <span className="text-gray-500">Model <span className="tabular-nums text-emerald-400">{pct(v?.modelProb, 0)}</span></span>
                          <span className="text-gray-500">{bookName} <span className="tabular-nums text-gray-300">{v?.bookDevig != null ? pct(v.bookDevig, 0) : "—"}</span></span>
                          {v?.line != null && <span className="text-gray-600">line {v.line}</span>}
                        </div>
                        <div className="mt-1.5 flex items-center gap-2">
                          <label className="text-[10px] text-gray-500">Odds</label>
                          <input
                            inputMode="numeric"
                            placeholder="-110"
                            value={l.odds}
                            onChange={(e) => setOdds(l.key, e.target.value.replace(/[^0-9+-]/g, ""))}
                            className="h-7 w-24 rounded border border-[#262626] bg-[#141414] px-2 text-xs tabular-nums text-white focus:border-sky-600 focus:outline-none"
                          />
                          <span className="text-[10px] text-gray-600">American</span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}

              {slip.length > 0 && (
                <div className="mt-3 rounded-md border border-[#1e1e1e] bg-[#0d0d0d] p-2.5">
                  <label className="text-[10px] uppercase tracking-wider text-gray-500">
                    {hasSameGame ? "Book's parlay odds (required for same-game)" : "Book's parlay odds (optional)"}
                  </label>
                  <div className="mt-1.5 flex items-center gap-2">
                    <input
                      inputMode="numeric"
                      placeholder="+265"
                      value={parlayOdds}
                      onChange={(e) => setParlayOdds(e.target.value.replace(/[^0-9+-]/g, ""))}
                      className="h-7 w-28 rounded border border-[#262626] bg-[#141414] px-2 text-xs tabular-nums text-white focus:border-sky-600 focus:outline-none"
                    />
                    <span className="text-[10px] text-gray-600">American</span>
                  </div>
                  {hasSameGame && (
                    <p className="mt-1.5 text-[10px] leading-relaxed text-amber-500/80">
                      This parlay has same-game legs. Sportsbooks price a same-game parlay with their own
                      correlation model, so its price can&apos;t be computed from the individual leg odds —
                      enter the book&apos;s posted parlay odds to see the implied probability and expected value.
                    </p>
                  )}
                </div>
              )}
            </div>

            {slip.length > 0 && result && <ResultPanel result={result} />}
          </section>
        </div>

        <div className="mt-8 flex items-start gap-2 rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2.5">
          <Info className="mt-0.5 h-3 w-3 shrink-0 text-gray-600" />
          <p className="text-[11px] leading-relaxed text-gray-500">
            {result?.disclaimer || universe?.disclaimer || DISCLAIMER_FALLBACK}
          </p>
        </div>
      </main>
    </>
  )
}

// ---------------------------------------------------------------------------
// Result panel
// ---------------------------------------------------------------------------

function ResultPanel({ result }: { result: EvalResult }) {
  const ev = result.expected_value_per_dollar
  const evColor = ev == null ? "text-gray-300" : ev < 0 ? "text-rose-400" : ev > 0 ? "text-emerald-400" : "text-gray-300"
  const evText = ev == null ? "—" : `${ev >= 0 ? "+" : ""}${(ev * 100).toFixed(1)}% / $1`

  return (
    <div className="mt-4 rounded-lg border border-[#262626] bg-[#111111] p-4">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-400">Result</h3>

      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded-md border border-[#1e1e1e] bg-[#0d0d0d] py-2.5">
          <div className="text-[10px] uppercase tracking-wider text-gray-600">True (model)</div>
          <div className="text-lg font-bold tabular-nums text-white">{pct(result.combined_true_prob)}</div>
        </div>
        <div className="rounded-md border border-[#1e1e1e] bg-[#0d0d0d] py-2.5">
          <div className="text-[10px] uppercase tracking-wider text-gray-600">Book implied</div>
          <div className="text-lg font-bold tabular-nums text-white">{pct(result.book_implied_prob)}</div>
        </div>
        <div className="rounded-md border border-[#1e1e1e] bg-[#0d0d0d] py-2.5">
          <div className="text-[10px] uppercase tracking-wider text-gray-600">Expected value</div>
          <div className={`text-lg font-bold tabular-nums ${evColor}`}>{evText}</div>
        </div>
      </div>

      {result.has_same_game && result.naive_independent_prob != null && (
        <div className="mt-3 flex items-center gap-2 rounded-md border border-amber-900/40 bg-amber-950/20 px-2.5 py-2">
          <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-300">
            Same-game correlation applied
          </span>
          <span className="text-[10px] leading-tight text-amber-200/80">
            Naive independence would show {pct(result.naive_independent_prob)}; correlation-adjusted to{" "}
            {pct(result.combined_true_prob)} with a conservative prior.
          </span>
        </div>
      )}

      <p className="mt-3 text-xs leading-relaxed text-gray-300">{result.verdict}</p>

      {result.flags.length > 0 && (
        <ul className="mt-2 space-y-1">
          {result.flags.map((f, i) => (
            <li key={i} className="flex items-start gap-1.5 text-[10px] leading-relaxed text-gray-500">
              <Info className="mt-0.5 h-2.5 w-2.5 shrink-0 text-gray-600" />
              <span>{f}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3 border-t border-[#1e1e1e] pt-2.5">
        <div className="mb-1 text-[10px] uppercase tracking-wider text-gray-600">Legs (model vs book)</div>
        <div className="space-y-1">
          {result.legs.map((l, i) => (
            <div key={i} className="flex items-center justify-between text-[11px]">
              <span className={`truncate ${l.resolved ? "text-gray-300" : "text-gray-600 line-through"}`}>
                {l.label ?? `${l.market_type} ${l.side}`}
              </span>
              <span className="ml-2 shrink-0 tabular-nums text-gray-500">
                {l.resolved ? <span className="text-emerald-400">{pct(l.hit_prob, 0)}</span> : "no model prob"}
                {l.book_implied_prob != null ? <> · book {pct(l.book_implied_prob, 0)}</> : ""}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function ParlayPage() {
  return (
    <AuthGuard>
      <ParlayPageInner />
    </AuthGuard>
  )
}
