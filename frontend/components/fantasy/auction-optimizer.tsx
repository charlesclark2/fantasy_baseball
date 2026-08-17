"use client"

// The live NFL-fantasy AUCTION optimizer (NF-C5). Sibling to the snake Draft Optimizer, not a mode
// of it: a snake draft allocates PICKS and an auction allocates MONEY, so the tool has to answer a
// different question ("how much may I pay for him?") with two quantities the snake tool has no
// analog for — the room's price INFLATION and an affordability cap that can never strand a roster
// spot.
//
// All client-side: the (config, size) board JSON loads once, then every completed sale recomputes
// values, inflation and every max bid instantly. `lib/auction-optimizer` is a faithful port of the
// validated Python engine and is pinned to it by a golden vector file — see that module's header.
//
// Honest framing: values are OUR valuation of OUR projections, and the band is the projection's own
// 80% interval priced at the league rate. We have NO model of what the room will actually pay, and
// nothing here claims to beat it.

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { RotateCcw, Undo2, Search } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Picker } from "@/components/ui/picker"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { InfoTip } from "@/components/fantasy/shared"
import { assignRoster, sortAvailable, type FilledSlot, type Player, type LeagueConfigMeta } from "@/lib/draft-optimizer"
import {
  auctionBoard,
  defaultSalePrice,
  formatInflation,
  formatMoney,
  formatMoneyRange,
  openSlotsFor,
  rosterSpotsOf,
  type AuctionPick,
  type TeamBudget,
} from "@/lib/auction-optimizer"
import {
  FANTASY_SEASON,
  isCustomSelection,
  useFantasyManifest,
  useResolvedBoard,
  useSavedLeagues,
} from "@/lib/fantasy-queries"

const SEASON = FANTASY_SEASON
const POS_COLORS: Record<string, string> = {
  QB: "text-rose-400 bg-rose-500/10 border-rose-500/30",
  RB: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  WR: "text-sky-400 bg-sky-500/10 border-sky-500/30",
  TE: "text-amber-400 bg-amber-500/10 border-amber-500/30",
  K: "text-violet-400 bg-violet-500/10 border-violet-500/30",
  DST: "text-teal-400 bg-teal-500/10 border-teal-500/30",
}
const FILTER_POSITIONS = ["QB", "RB", "WR", "TE", "K", "DST"] as const
const BUDGET_CHOICES = [100, 150, 200, 260, 300] as const

const teamLabel = (p: { team: string | null; rookie: boolean }) => p.team ?? (p.rookie ? "Rk" : "FA")

interface AuctionState {
  configName: string
  size: number
  budget: number
  myTeam: number
  picks: AuctionPick[]
}

const storageKey = (s: { configName: string; size: number; budget: number; myTeam: number }) =>
  `nfl-auction-${SEASON}-${s.configName}-${s.size}-b${s.budget}-t${s.myTeam}`

export function AuctionOptimizer() {
  const { data: manifest, isLoading: manifestLoading, error: manifestError } = useFantasyManifest()

  const [started, setStarted] = useState(false)
  const [configName, setConfigName] = useState<string>("")
  const [size, setSize] = useState<number>(12)
  const [budget, setBudget] = useState<number>(200)
  const [myTeam, setMyTeam] = useState<number>(1)
  const [picks, setPicks] = useState<AuctionPick[]>([])
  const [search, setSearch] = useState("")
  const [posFilter, setPosFilter] = useState<string>("ALL")
  // Per-row price entry, keyed by player id — an auction is recorded as "who, and for how much".
  const [prices, setPrices] = useState<Record<string, string>>({})

  useEffect(() => {
    if (manifest && !configName) {
      setConfigName(
        manifest.configs.find((c) => c.name === "half_ppr")?.name ?? manifest.configs[0]?.name ?? "",
      )
      setSize(manifest.sizes.includes(12) ? 12 : manifest.sizes[0])
    }
  }, [manifest, configName])

  // A hand-entered league auctions exactly like a preset — `useResolvedBoard` returns the same
  // `Player[]` from either source (NF-C0b).
  const { data: savedLeagues } = useSavedLeagues()
  const selectedLeague = isCustomSelection(configName)
    ? savedLeagues?.find((l) => `custom:${l.league_id}` === configName)
    : undefined

  const config: LeagueConfigMeta | undefined = selectedLeague
    ? {
        name: configName,
        label: selectedLeague.name,
        ppr: selectedLeague.ppr,
        superflex: selectedLeague.superflex,
        description: `Your saved settings — ${selectedLeague.n_teams}-team.`,
        roster: selectedLeague.roster,
      }
    : manifest?.configs.find((c) => c.name === configName)

  useEffect(() => {
    if (selectedLeague && size !== selectedLeague.n_teams) {
      setSize(selectedLeague.n_teams)
      setMyTeam((t) => Math.min(t, selectedLeague.n_teams))
    }
  }, [selectedLeague, size])

  const { board, isLoading: boardLoading } = useResolvedBoard(
    started ? configName : null,
    started ? size : null,
  )

  // restore / persist — people reload mid-auction, and losing the money is worse than losing picks
  useEffect(() => {
    if (!started) return
    try {
      const raw = localStorage.getItem(storageKey({ configName, size, budget, myTeam }))
      setPicks(raw ? (JSON.parse(raw) as AuctionState).picks ?? [] : [])
    } catch {
      setPicks([])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [started, configName, size, budget, myTeam])

  useEffect(() => {
    if (!started) return
    try {
      localStorage.setItem(
        storageKey({ configName, size, budget, myTeam }),
        JSON.stringify({ configName, size, budget, myTeam, picks } as AuctionState),
      )
    } catch {
      /* ignore quota */
    }
  }, [started, configName, size, budget, myTeam, picks])

  // ⭐ EVERYTHING ON SCREEN COMES FROM ONE CALL. Values, inflation, every team's money, the max bid
  // and its reason are all derived together from (board, config, picks) — so no two panels can ever
  // be describing different states of the same auction.
  const state = useMemo(() => {
    if (!board || !config) return null
    return auctionBoard({ board, config, nTeams: size, budget, myTeam, picks, topN: 8 })
  }, [board, config, size, budget, myTeam, picks])

  const byId = useMemo(() => new Map((board ?? []).map((p) => [p.id, p])), [board])
  const soldIds = useMemo(() => new Set(picks.map((p) => p.id)), [picks])
  const slotsPerTeam = config ? rosterSpotsOf(config) : 0
  const auctionComplete = !!state && state.budgets.every((b) => b.openSlots === 0)

  const filledRoster: FilledSlot[] = useMemo(
    () => (config && state ? assignRoster(state.myPlayers, config.roster) : []),
    [config, state],
  )
  const openSlots = useMemo(
    () => (config && state ? openSlotsFor(state.myPlayers, config) : null),
    [config, state],
  )

  const priceFor = useCallback(
    (id: string, fallback: number) => {
      const raw = prices[id]
      const n = raw == null || raw === "" ? fallback : Number(raw)
      return Number.isFinite(n) && n >= 0 ? Math.floor(n) : fallback
    },
    [prices],
  )

  const sell = useCallback(
    (id: string, team: number, price: number) => {
      setPicks((prev) => {
        if (prev.some((p) => p.id === id)) return prev // already sold — guard a double-click
        return [...prev, { id, team, price: Math.max(0, Math.floor(price)) }]
      })
      setPrices((prev) => {
        const next = { ...prev }
        delete next[id]
        return next
      })
    },
    [],
  )
  const undo = useCallback(() => setPicks((prev) => prev.slice(0, -1)), [])
  const reset = useCallback(() => {
    if (confirm("Reset this auction? Every recorded sale will be cleared.")) setPicks([])
  }, [])

  const available = useMemo(() => {
    const rows = (board ?? []).filter((p) => !soldIds.has(p.id))
    const q = search.trim().toLowerCase()
    const filtered = rows.filter(
      (p) => (posFilter === "ALL" || p.pos === posFilter) && (!q || p.name.toLowerCase().includes(q)),
    )
    // The shared ordering, so best-available and the recommendations cannot disagree about K/DST.
    return sortAvailable(filtered, {
      sortCol: "vor",
      sortDir: "desc",
      deferLowPred: posFilter !== "K" && posFilter !== "DST",
    })
  }, [board, soldIds, search, posFilter])

  // ── SETUP ─────────────────────────────────────────────────────────────────────────────────────
  if (!started) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-10">
        <h1 className="text-2xl font-semibold text-white">Auction Optimizer</h1>
        <p className="mt-2 text-sm text-gray-400">
          Track an auction live. Every time a player sells, the tool re-prices the board: what the
          room has left to spend against what is left to buy, and the most you can bid on anyone
          without leaving a roster spot you cannot fill.
        </p>
        <div className="mt-6 rounded-lg border border-[#262626] bg-[#0f0f0f] p-5">
          {manifestLoading && <p className="text-sm text-gray-500">Loading league presets…</p>}
          {manifestError && (
            <p className="text-sm text-rose-400">Could not load the {SEASON} draft boards.</p>
          )}
          {manifest && config && (
            <div className="flex flex-col gap-4">
              <Field label="League format">
                <Picker
                  value={configName}
                  onValueChange={setConfigName}
                  ariaLabel="Scoring format"
                  className="w-full rounded-md border border-[#262626] bg-[#0a0a0a] px-3 py-2 text-base sm:text-sm text-white"
                  groups={[
                    {
                      label: "Your leagues",
                      options: (savedLeagues ?? []).map((l) => ({
                        value: `custom:${l.league_id}`,
                        label: `${l.name} (${l.n_teams}-team)`,
                      })),
                    },
                    {
                      label: "Standard formats",
                      options: manifest.configs.map((c) => ({ value: c.name, label: c.label })),
                    },
                  ]}
                />
                <p className="mt-1 text-xs text-gray-500">
                  {config.description}
                  {!selectedLeague && (
                    <>
                      {" "}
                      Not your league?{" "}
                      <a href="/fantasy/league-settings" className="text-sky-400 hover:underline">
                        Enter its settings
                      </a>
                      .
                    </>
                  )}
                </p>
              </Field>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <Field label="League size">
                  <Picker
                    value={String(size)}
                    onValueChange={(v) => setSize(Number(v))}
                    disabled={!!selectedLeague}
                    ariaLabel="League size"
                    className="w-full rounded-md border border-[#262626] bg-[#0a0a0a] px-3 py-2 text-base sm:text-sm text-white disabled:opacity-60"
                    options={(selectedLeague ? [selectedLeague.n_teams] : manifest.sizes).map((s) => ({
                      value: String(s),
                      label: `${s} teams`,
                    }))}
                  />
                </Field>
                <Field label="Budget per team">
                  <Picker
                    value={String(budget)}
                    onValueChange={(v) => setBudget(Number(v))}
                    ariaLabel="Auction budget"
                    className="w-full rounded-md border border-[#262626] bg-[#0a0a0a] px-3 py-2 text-base sm:text-sm text-white"
                    options={BUDGET_CHOICES.map((b) => ({ value: String(b), label: `$${b}` }))}
                  />
                </Field>
                <Field label="You are team">
                  <Picker
                    value={String(myTeam)}
                    onValueChange={(v) => setMyTeam(Number(v))}
                    ariaLabel="My team"
                    className="w-full rounded-md border border-[#262626] bg-[#0a0a0a] px-3 py-2 text-base sm:text-sm text-white"
                    options={Array.from({ length: size }, (_, i) => i + 1).map((s) => ({
                      value: String(s),
                      label: `Team ${s}`,
                    }))}
                  />
                </Field>
              </div>
              <p className="text-xs text-gray-500">
                {size} teams × ${budget} = <span className="text-gray-300">${size * budget}</span> in
                the room, for {size * slotsPerTeam} roster spots.
              </p>
              <Button
                onClick={() => setStarted(true)}
                className="mt-2 bg-[#10b981] font-semibold text-[#0a0a0a] hover:bg-[#059669]"
              >
                Start auction
              </Button>
            </div>
          )}
        </div>
        <HonestNote />
      </div>
    )
  }

  // ── AUCTION ───────────────────────────────────────────────────────────────────────────────────
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#262626] bg-[#0f0f0f] px-4 py-3">
        <div className="flex items-center gap-4">
          <button
            onClick={() => setStarted(false)}
            className="text-xs text-gray-500 hover:text-gray-300"
          >
            ← Setup
          </button>
          <div>
            <div className="text-sm font-medium text-white">{config?.label}</div>
            <div className="text-xs text-gray-500">
              {size}-team · ${budget} budget · you are team #{myTeam}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <Stat label="Your budget">
            <span data-testid="auction-budget-remaining" className="text-[#10b981]">
              {formatMoney(state?.me.remaining ?? budget)}
            </span>
          </Stat>
          <Stat label="Open slots">
            <span data-testid="auction-open-slots">{state?.me.openSlots ?? slotsPerTeam}</span>
          </Stat>
          <Stat label="Per slot">{formatMoney(state?.perSlot ?? budget / (slotsPerTeam || 1))}</Stat>
          <Stat
            label={
              <span className="inline-flex items-center gap-1">
                Prices
                <InfoTip label={null}>
                  <strong>Inflation</strong> is the money still in the room divided by the value
                  still on the board. It starts at <strong>1.00x</strong> because the values are
                  built to spend exactly this room&apos;s budget. Below 1.00x the room has
                  <em> overspent</em>, so what is left is going for less than it is worth; above
                  1.00x the room has been thrifty and the rest will cost over sticker. This is a
                  statement about money already spent — not a forecast of what anyone will bid.
                </InfoTip>
              </span>
            }
          >
            <span
              data-testid="auction-inflation"
              className={
                (state?.inflation.multiplier ?? 1) < 0.97
                  ? "text-emerald-400"
                  : (state?.inflation.multiplier ?? 1) > 1.05
                    ? "text-amber-400"
                    : "text-white"
              }
            >
              {formatInflation(state?.inflation.multiplier ?? 1)}
            </span>
          </Stat>
          <Button
            variant="ghost"
            size="sm"
            onClick={undo}
            disabled={!picks.length}
            className="text-gray-400 hover:text-white"
          >
            <Undo2 className="mr-1 h-3.5 w-3.5" /> Undo
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={reset}
            disabled={!picks.length}
            className="text-gray-400 hover:text-white"
          >
            <RotateCcw className="mr-1 h-3.5 w-3.5" /> Reset
          </Button>
        </div>
      </div>

      {auctionComplete && (
        <div className="mt-3 rounded-lg border border-[#10b981]/50 bg-[#10b981]/10 px-4 py-2.5 text-sm font-semibold text-[#10b981]">
          🎉 Every roster is full — the auction is complete.
        </div>
      )}

      {boardLoading && <p className="mt-6 text-sm text-gray-500">Loading board…</p>}

      {board && config && state && (
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
          {/* ⚠️ `min-w-0` IS LOAD-BEARING. A grid item's automatic minimum is its MIN-CONTENT width,
              and `truncate` (white-space: nowrap) makes the min-content of a why-this-bid sentence
              the FULL sentence — so the `1fr` track grows to fit it, the grid overflows
              `max-w-6xl`, and the whole page gets a horizontal scrollbar with the roster panel
              pushed off screen. Measured at 2129px on the snake optimizer before its fix. ⛔
              `min-w-0` on an inner flex child is NOT enough: that removes the item's automatic
              minimum for FLEX layout, it does not reduce the GRID track's intrinsic minimum. */}
          <div className="flex min-w-0 flex-col gap-4">
            {/* ── candidates + max bid ─────────────────────────────────────────────────────── */}
            <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
              <div className="mb-3 flex items-center gap-2">
                <h2 className="text-sm font-semibold text-white">Your max bid</h2>
                <InfoTip label={null}>
                  Ranked by what your roster needs next — the same value-over-replacement, tier-cliff
                  and roster-need reading the snake Draft Optimizer uses. The <strong>bid</strong> is
                  the smaller of two numbers: the player&apos;s value at today&apos;s prices, and the
                  most you can pay while still leaving $1 for every other slot you have to fill. The
                  second one is a hard rule — an empty starter slot scores nothing, so the tool will
                  never walk you into one. Values are our valuation of our projections; we have no
                  model of what the room will actually pay. Not betting advice.
                </InfoTip>
              </div>
              <div className="flex flex-col gap-2">
                {state.candidates.map((c, i) => (
                  <div
                    key={c.player.id}
                    data-testid="auction-candidate"
                    className={`flex flex-wrap items-center gap-3 rounded-md border px-3 py-2 ${
                      i === 0 ? "border-[#10b981]/40 bg-[#10b981]/5" : "border-[#1f1f1f] bg-[#0a0a0a]"
                    }`}
                  >
                    <PosBadge pos={c.player.pos} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span
                          data-testid="auction-candidate-name"
                          className="truncate text-sm font-medium text-white"
                        >
                          {c.player.name}
                        </span>
                        <span className="whitespace-nowrap text-xs text-gray-600">
                          {teamLabel(c.player)} · {c.player.pos}
                          {c.player.posRank}
                        </span>
                      </div>
                      {/* ⚠️ `truncate` here is what makes the `min-w-0` above load-bearing. */}
                      <div className="truncate text-xs text-gray-500">{c.why}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] uppercase tracking-wide text-gray-600">Value</div>
                      <div className="text-xs text-gray-300">
                        {formatMoneyRange(c.auction.low, c.auction.high)}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] uppercase tracking-wide text-gray-600">Max bid</div>
                      <div
                        data-testid="auction-max-bid"
                        className={`text-sm font-semibold ${
                          c.bid.maxBid > 0 ? "text-white" : "text-gray-600"
                        }`}
                      >
                        {formatMoney(c.bid.maxBid)}
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className="text-xs text-gray-600">$</span>
                      <input
                        data-testid="auction-price-input"
                        data-player={c.player.id}
                        inputMode="numeric"
                        aria-label={`Winning price for ${c.player.name}`}
                        value={prices[c.player.id] ?? ""}
                        placeholder={String(defaultSalePrice(c.bid))}
                        onChange={(e) =>
                          setPrices((p) => ({ ...p, [c.player.id]: e.target.value }))
                        }
                        className="w-14 rounded border border-[#262626] bg-[#0a0a0a] px-1.5 py-1 text-base sm:text-xs text-white placeholder:text-gray-700"
                      />
                      <Button
                        data-testid="auction-win-button"
                        size="sm"
                        onClick={() =>
                          sell(c.player.id, myTeam, priceFor(c.player.id, defaultSalePrice(c.bid)))
                        }
                        // ⚠️ Only "I WON" is gated on eligibility — "Sold" (a rival's win) is not,
                        // and must not be: whether a player fits MY roster says nothing about
                        // whether someone else bought him, and refusing to record a real sale
                        // would silently stop the room's prices updating.
                        disabled={!c.eligible}
                        title={
                          c.eligible ? undefined : "No open slot on your roster fits this position"
                        }
                        className="bg-[#10b981] font-semibold text-[#0a0a0a] hover:bg-[#059669] disabled:opacity-40"
                      >
                        I won
                      </Button>
                      <SoldToMenu
                        budgets={state.budgets}
                        myTeam={myTeam}
                        onSell={(team) =>
                          sell(c.player.id, team, priceFor(c.player.id, defaultSalePrice(c.bid)))
                        }
                      />
                    </div>
                  </div>
                ))}
                {!state.candidates.length && (
                  <p className="text-sm text-gray-500">No players left to bid on.</p>
                )}
              </div>
            </div>

            {/* ── available board ──────────────────────────────────────────────────────────── */}
            <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <h2 className="mr-auto text-sm font-semibold text-white">Available players</h2>
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-600" />
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search…"
                    aria-label="Search players"
                    className="w-40 rounded-md border border-[#262626] bg-[#0a0a0a] py-1.5 pl-7 pr-2 text-base sm:text-xs text-white placeholder:text-gray-600"
                  />
                </div>
                <div className="flex flex-wrap gap-1">
                  {["ALL", ...FILTER_POSITIONS].map((p) => (
                    <button
                      key={p}
                      onClick={() => setPosFilter(p)}
                      className={`rounded px-2 py-1 text-xs font-medium ${
                        posFilter === p
                          ? "bg-[#10b981] text-[#0a0a0a]"
                          : "bg-[#1a1a1a] text-gray-400 hover:text-white"
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
              <p className="mb-2 text-[11px] leading-snug text-gray-600">
                <strong className="text-gray-500">Value</strong> is the range this player is worth in
                a ${budget} league — his projection&apos;s own 80% interval priced at the
                league&apos;s dollars-per-point. It is what he is <em>worth</em>, not a forecast of
                what he will <em>go for</em>.
              </p>
              <p className="mb-2 text-[11px] leading-snug text-gray-600">
                Someone nominated a name that isn&apos;t on the shortlist? Search for him, type what
                he actually sold for, and record who won him. Leave the box empty and we record what
                he is worth at today&apos;s prices — the greyed-out number.
              </p>
              {/* The table scrolls inside its OWN box, so a wide row can never widen the page. */}
              <div className="max-h-[520px] overflow-y-auto overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-[#0f0f0f] text-left text-[11px] uppercase tracking-wide text-gray-600">
                    <tr>
                      <th className="py-1.5 pl-1 font-medium">#</th>
                      <th className="py-1.5 font-medium">Player</th>
                      <th className="py-1.5 text-right font-medium">Value</th>
                      <th className="py-1.5 text-right font-medium">Your max</th>
                      <th className="py-1.5 text-right font-medium">Sold for</th>
                      <th className="py-1.5 pr-1 text-right font-medium"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {available.slice(0, 250).map((p) => {
                      const v = state.values.get(p.id)
                      const bid = state.bidFor(p)
                      return (
                        <tr key={p.id} className="border-t border-[#171717] hover:bg-[#141414]">
                          <td className="py-1.5 pl-1 text-xs text-gray-600">
                            {p.lowPred ? "—" : p.ovrRank}
                          </td>
                          <td className="py-1.5">
                            <div className="flex items-center gap-2">
                              <PosBadge pos={p.pos} small />
                              <Link
                                href={`/fantasy/player/${p.id}`}
                                className="text-white hover:text-[#10b981] hover:underline"
                              >
                                {p.name}
                              </Link>
                              <span className="whitespace-nowrap text-xs text-gray-600">
                                {teamLabel(p)}
                                {p.posRank ? ` · ${p.pos}${p.posRank}` : ""}
                              </span>
                            </div>
                          </td>
                          <td className="whitespace-nowrap py-1.5 text-right text-gray-300">
                            {formatMoneyRange(v?.low, v?.high)}
                          </td>
                          {/* ⭐ THE SHARED `bidFor`, never an inline recompute. The first cut
                              did the arithmetic here and reached a DIFFERENT number than the panel
                              above (it applied the affordability cap but neither inflation nor the
                              eligibility check), so one player showed two max bids three rows
                              apart — the E9.61 two-renderers defect on the number a user bids
                              money against. */}
                          <td
                            data-testid="auction-board-max-bid"
                            data-player={p.id}
                            className="py-1.5 text-right text-gray-400"
                          >
                            {formatMoney(bid.maxBid)}
                          </td>
                          {/* ⭐ THE PRICE BOX, ON EVERY ROW. Reported live 2026-08-17: a nomination
                              is very often NOT one of the top few names, so the only way to record
                              it was this table — which had no price entry at all, silently writing
                              a default. A recorded auction is "who, and for how much"; a surface
                              that can record only the "who" is not a record of an auction.
                              ⚠️ SAME `prices` state and SAME `priceFor` as the panel above, not a
                              second price mechanism (E9.61). */}
                          <td className="py-1.5 text-right">
                            <div className="flex items-center justify-end gap-1">
                              <span className="text-xs text-gray-600">$</span>
                              <input
                                data-testid="auction-price-input"
                                data-player={p.id}
                                inputMode="numeric"
                                aria-label={`Sale price for ${p.name}`}
                                value={prices[p.id] ?? ""}
                                placeholder={String(defaultSalePrice(bid))}
                                onChange={(e) =>
                                  setPrices((prev) => ({ ...prev, [p.id]: e.target.value }))
                                }
                                className="w-14 rounded border border-[#262626] bg-[#0a0a0a] px-1.5 py-1 text-base sm:text-xs text-white placeholder:text-gray-700"
                              />
                            </div>
                          </td>
                          {/* ⭐ BOTH OUTCOMES, FOR EVERY PLAYER. The recommendation panel only ever
                              lists the top few candidates for MY roster, so with "Sold" available
                              there alone a rival buying anyone else could not be recorded AT ALL —
                              and an unrecorded sale is a player who stays biddable and a room whose
                              prices never move. Reported live 2026-08-17 alongside the team-
                              attribution defect; they are the same gap seen from two sides. */}
                          <td className="py-1.5 pr-1 text-right">
                            <div className="flex items-center justify-end gap-1">
                              <button
                                data-testid="auction-board-win-button"
                                data-player={p.id}
                                onClick={() =>
                                  sell(p.id, myTeam, priceFor(p.id, defaultSalePrice(bid)))
                                }
                                disabled={!state.openEligibility.has(p.pos)}
                                className="rounded border border-[#2a2a2a] px-2 py-0.5 text-xs text-gray-400 hover:border-[#10b981] hover:text-[#10b981] disabled:opacity-30 disabled:hover:border-[#2a2a2a] disabled:hover:text-gray-400"
                                title={
                                  state.openEligibility.has(p.pos)
                                    ? `Record ${p.name} sold to you for the price shown`
                                    : "No open slot on your roster fits this position"
                                }
                              >
                                I won
                              </button>
                              <SoldToMenu
                                budgets={state.budgets}
                                myTeam={myTeam}
                                onSell={(team) =>
                                  sell(p.id, team, priceFor(p.id, defaultSalePrice(bid)))
                                }
                              />
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                {available.length > 250 && (
                  <p className="py-2 text-center text-xs text-gray-600">
                    Showing top 250 — search to find the rest.
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* RIGHT */}
          <div className="flex min-w-0 flex-col gap-4">
            <NominationPanel plan={state.nomination} />
            <RosterPanel
              filled={filledRoster}
              openSlots={openSlots}
              spent={state.me.spent}
              remaining={state.me.remaining}
            />
            <RoomPanel budgets={state.budgets} myTeam={myTeam} />
            <RecentSales picks={picks} byId={byId} myTeam={myTeam} />
          </div>
        </div>
      )}
      <HonestNote />
    </div>
  )
}

// ── sub-components ──────────────────────────────────────────────────────────────────────────────
/**
 * "Sold" → pick the winning team → recorded.
 *
 * ⭐ WHY A MENU AND NOT A REMEMBERED SETTING. The first cut hardcoded the buyer
 * (`myTeam === 1 ? 2 : 1`), so EVERY rival purchase piled onto one team: the room panel was wrong,
 * and once that team passed its roster size its extra buys became invisible to `openSlots` — the
 * denominator `inflation` divides by. Reported live 2026-08-17.
 *
 * A persistent "sold to team N" selector would fix the arithmetic and introduce a worse failure:
 * it goes stale silently, and the next sale is attributed to whoever won the last one. Asking every
 * time is one extra click on an action that already needs a deliberate price, and it cannot be
 * wrong by omission.
 *
 * ⛔ A TEAM WITH NO OPEN SLOT IS NOT OFFERED. That is what makes the over-capacity state
 * unreachable from the UI rather than merely clamped in the arithmetic; each team's remaining money
 * is shown beside it so a mis-click is visible before it is made.
 *
 * ONE component for both the recommendation panel and the available-players table — two "record a
 * sale" implementations would be two rule sets (E9.61).
 */
function SoldToMenu({
  budgets,
  myTeam,
  onSell,
  label = "Sold",
}: {
  budgets: TeamBudget[]
  myTeam: number
  onSell: (team: number) => void
  label?: string
}) {
  const rivals = budgets.filter((b) => b.team !== myTeam)
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        data-testid="auction-rival-button"
        title="Someone else won him — record the sale so the room's prices update"
        className="rounded border border-[#2a2a2a] px-2 py-1 text-xs text-gray-400 hover:border-[#10b981] hover:text-[#10b981]"
      >
        {label}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[11rem] border-[#262626] bg-[#0f0f0f]">
        <DropdownMenuLabel className="text-[11px] uppercase tracking-wide text-gray-500">
          Sold to
        </DropdownMenuLabel>
        {rivals.map((b) => (
          <DropdownMenuItem
            key={b.team}
            data-testid="auction-rival-team"
            data-team={b.team}
            disabled={b.openSlots === 0}
            onSelect={() => onSell(b.team)}
            className="flex justify-between gap-4 text-xs text-gray-300 focus:bg-[#1a1a1a] focus:text-white"
          >
            <span>Team {b.team}</span>
            <span className="text-gray-500">
              {b.openSlots === 0 ? "roster full" : `${formatMoney(b.remaining)} · ${b.openSlots} slots`}
            </span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-gray-500">
        {label}
      </span>
      {children}
    </label>
  )
}

function Stat({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="text-right">
      <div className="text-[10px] uppercase tracking-wide text-gray-600">{label}</div>
      <div className="text-sm font-semibold text-white">{children}</div>
    </div>
  )
}

function PosBadge({ pos, small }: { pos: string; small?: boolean }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded border font-semibold ${
        POS_COLORS[pos] ?? "text-gray-400 bg-gray-500/10 border-gray-500/30"
      } ${small ? "h-5 w-8 text-[10px]" : "h-6 w-9 text-xs"}`}
    >
      {pos}
    </span>
  )
}

function NominationPanel({ plan }: { plan: ReturnType<typeof auctionBoard>["nomination"] }) {
  const title =
    plan.mode === "target"
      ? "Nominate: your targets"
      : plan.mode === "drain"
        ? "Nominate: drain the room"
        : "Nominate: from your depth"
  return (
    <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
      <div className="mb-2 flex items-center gap-2">
        <h2 className="text-sm font-semibold text-white">{title}</h2>
        <InfoTip label={null}>
          Who to put up for bidding. When prices are <strong>below</strong> value the room has
          overspent, so nominating a player you want lets the discount come to you. When your money
          per open slot is <strong>above</strong> the room&apos;s, your advantage is relative — so
          put up expensive players you do <em>not</em> need and let everyone else spend first.
          Otherwise nominate from a position you are already deep at.
        </InfoTip>
      </div>
      <p className="mb-2 text-[11px] leading-snug text-gray-500">{plan.reason}</p>
      <div className="flex flex-col gap-1">
        {plan.players.map((p) => (
          <div key={p.id} className="flex items-center gap-2 text-xs">
            <PosBadge pos={p.pos} small />
            <span className="truncate text-gray-300">{p.name}</span>
          </div>
        ))}
        {!plan.players.length && <p className="text-xs text-gray-600">Nothing left to nominate.</p>}
      </div>
    </div>
  )
}

function RosterPanel({
  filled,
  openSlots,
  spent,
  remaining,
}: {
  filled: FilledSlot[]
  openSlots: ReturnType<typeof openSlotsFor> | null
  spent: number
  remaining: number
}) {
  const needs: string[] = []
  if (openSlots) {
    for (const [pos, n] of Object.entries(openSlots.dedicated)) needs.push(n > 1 ? `${n}× ${pos}` : pos)
    if (openSlots.flex.length) needs.push(`${openSlots.flex.length}× FLEX`)
  }
  return (
    <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-4" data-testid="auction-roster">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-white">Your team</h2>
        <span className="text-xs text-gray-500">
          {formatMoney(spent)} spent · {formatMoney(remaining)} left
        </span>
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-gray-500">Needs:</span>
        {needs.length ? (
          needs.map((n) => (
            <span key={n} className="rounded bg-[#10b981]/10 px-1.5 py-0.5 text-xs text-[#10b981]">
              {n}
            </span>
          ))
        ) : (
          <span className="text-xs text-gray-500">starters set</span>
        )}
      </div>
      <div className="flex flex-col gap-1">
        {filled.map((s, i) => (
          <div
            key={i}
            className="flex items-center gap-2 rounded border border-[#1a1a1a] bg-[#0a0a0a] px-2 py-1.5"
          >
            <span className="w-12 shrink-0 text-[11px] font-medium uppercase text-gray-500">
              {s.slotName}
            </span>
            {s.player ? (
              <>
                <PosBadge pos={s.player.pos} small />
                <span className="truncate text-sm text-white">{s.player.name}</span>
              </>
            ) : (
              <span className="text-xs text-gray-700">empty</span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function RoomPanel({
  budgets,
  myTeam,
}: {
  budgets: ReturnType<typeof auctionBoard>["budgets"]
  myTeam: number
}) {
  const max = Math.max(1, ...budgets.map((b) => b.remaining))
  return (
    <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
      <h2 className="mb-2 text-sm font-semibold text-white">The room</h2>
      <div className="flex flex-col gap-1">
        {budgets.map((b) => (
          <div
            key={b.team}
            data-testid="auction-room-team"
            data-team={b.team}
            className="flex items-center gap-2 text-xs"
          >
            <span className={`w-10 shrink-0 ${b.team === myTeam ? "text-[#10b981]" : "text-gray-500"}`}>
              T{b.team}
            </span>
            <div className="h-1.5 min-w-0 flex-1 rounded bg-[#1a1a1a]">
              <div
                className={`h-1.5 rounded ${b.team === myTeam ? "bg-[#10b981]" : "bg-gray-600"}`}
                style={{ width: `${(b.remaining / max) * 100}%` }}
              />
            </div>
            <span className="w-16 shrink-0 text-right text-gray-400">
              {/* An overspend can only come from a hand-entered price, so it is SHOWN rather than
                  silently absorbed — the arithmetic floors `remaining` at 0, and a floor nobody can
                  see is indistinguishable from a real zero. */}
              <span data-testid="auction-room-remaining">
                {b.overspent ? (
                  <span
                    className="text-amber-400"
                    title={`Recorded prices total ${formatMoney(b.spent)} — more than this team's budget. Check a price you entered.`}
                  >
                    over
                  </span>
                ) : (
                  formatMoney(b.remaining)
                )}
              </span>
              <span className="text-gray-700">/{b.openSlots}</span>
            </span>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[10px] leading-snug text-gray-600">
        Money left / open slots. Only sales you record are counted.
      </p>
    </div>
  )
}

function RecentSales({
  picks,
  byId,
  myTeam,
}: {
  picks: AuctionPick[]
  byId: Map<string, Player>
  myTeam: number
}) {
  if (!picks.length) return null
  const recent = [...picks].slice(-12).reverse()
  return (
    <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
      <h2 className="mb-2 text-sm font-semibold text-white">Recent sales</h2>
      <div className="flex flex-col gap-1">
        {recent.map((p, i) => (
          <div key={`${p.id}-${i}`} className="flex items-center gap-2 text-xs">
            <span className={p.team === myTeam ? "font-medium text-[#10b981]" : "text-gray-400"}>
              T{p.team}
            </span>
            <span className="truncate text-gray-300">{byId.get(p.id)?.name ?? p.id}</span>
            <span className="ml-auto shrink-0 text-gray-500">{formatMoney(p.price)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function HonestNote() {
  return (
    <p className="mx-auto mt-8 max-w-3xl text-center text-[11px] leading-relaxed text-gray-600">
      Auction values are our valuation of our own projections — the league&apos;s contested money
      shared out by each player&apos;s value above replacement, with the range coming from the
      projection&apos;s own 80% interval. We do not model what your room will actually pay, so a
      value is what a player is <em>worth</em>, never a prediction of his price. This is analysis,
      not betting advice.
    </p>
  )
}
