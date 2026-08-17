"use client"

// The live NFL-fantasy draft optimizer (NF-C2 / MVP-3). All client-side: the (config, size) board JSON
// loads once, then every pick recomputes recommendations instantly (no server round-trip) — fast enough
// for a live draft. A manual draft tracker records picks in snake order; when you're on the clock the
// optimizer surfaces the value-maximizing pick given your roster needs + positional scarcity (VONA /
// tier cliffs), with honest uncertainty. Pre-draft it doubles as a tiered cheat sheet.
//
// Honest framing: this is a PROJECTION product (NF-FASTPATH → NF-C1). Ranks are trustworthy; the VOR
// interval is a first-order estimate (not yet calibrated); K/DST carry a BASE projection (NF1.6).

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { RotateCcw, Undo2, Search } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Picker } from "@/components/ui/picker"
import { InfoTip } from "@/components/fantasy/shared"
import {
  assignRoster,
  recommend,
  rosterRequirements,
  openStarterSlots,
  picksUntilNext,
  slotOnClock,
  sortAvailable,
  type FilledSlot,
  type Player,
  type LeagueConfigMeta,
} from "@/lib/draft-optimizer"
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
const POSITIONS = ["QB", "RB", "WR", "TE"] as const
const FILTER_POSITIONS = ["QB", "RB", "WR", "TE", "K", "DST"] as const

// A player's team for display: real abbreviation, or an honest label for the unteamed. Rookie team_id
// is not yet populated in the projection (upstream fix), so a rookie shows "Rk", never a wrong "FA".
const teamLabel = (p: { team: string | null; rookie: boolean }) => p.team ?? (p.rookie ? "Rk" : "FA")
const byeLabel = (bye: number | null | undefined) => (bye != null ? `Bye ${bye}` : "")

interface Pick {
  id: string
  slot: number
}

interface DraftState {
  configName: string
  size: number
  mySlot: number
  picks: Pick[]
}

const storageKey = (s: { configName: string; size: number; mySlot: number }) =>
  `nfl-draft-${SEASON}-${s.configName}-${s.size}-slot${s.mySlot}`

// ── data hooks ────────────────────────────────────────────────────────────────────────────────
// Boards load through the SERVER-SIDE-GATED backend (/fantasy/nfl/*, require_fantasy_access →
// 403) rather than the old public JSON, so the paid gate can't be bypassed at the asset URL.
// The hooks themselves are shared with the NF3 browse surfaces (lib/fantasy-queries).
const useManifest = useFantasyManifest

// ⭐ `assignRoster` / `FilledSlot` moved to `lib/draft-optimizer` at NF-C2.1 — the mock draft's CPU
// and its post-draft grade ask the same question, and a second copy would let them disagree.

// ── main component ──────────────────────────────────────────────────────────────────────────────
export function DraftOptimizer() {
  const { data: manifest, isLoading: manifestLoading, error: manifestError } = useManifest()

  const [started, setStarted] = useState(false)
  const [configName, setConfigName] = useState<string>("")
  const [size, setSize] = useState<number>(12)
  const [mySlot, setMySlot] = useState<number>(1)
  const [picks, setPicks] = useState<Pick[]>([])
  const [search, setSearch] = useState("")
  const [posFilter, setPosFilter] = useState<string>("ALL")
  const [sortCol, setSortCol] = useState<"ovrRank" | "pts" | "vor">("ovrRank")
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc")

  // default the config once the manifest lands
  useEffect(() => {
    if (manifest && !configName) {
      setConfigName(manifest.configs.find((c) => c.name === "half_ppr")?.name ?? manifest.configs[0]?.name ?? "")
      setSize(manifest.sizes.includes(12) ? 12 : manifest.sizes[0])
    }
  }, [manifest, configName])

  // ── NF-C0b: a hand-entered league drafts exactly like a preset ────────────────────────────────
  // `useResolvedBoard` returns the same Player[] from either source, and the saved league's own
  // roster is presented as a `LeagueConfigMeta`, so every downstream calculation in this component
  // (roster needs, slots-per-team, the recommendation engine) is untouched by the distinction.
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

  // A saved league carries its OWN team count; keep the draft's size in step with it so the snake
  // order and the pick budget match the league the user actually entered.
  useEffect(() => {
    if (selectedLeague && size !== selectedLeague.n_teams) {
      setSize(selectedLeague.n_teams)
      setMySlot((s) => Math.min(s, selectedLeague.n_teams))
    }
  }, [selectedLeague, size])

  const { board, isLoading: boardLoading } = useResolvedBoard(
    started ? configName : null,
    started ? size : null,
  )

  // restore an in-progress draft for this exact (config, size, slot)
  useEffect(() => {
    if (!started) return
    try {
      const raw = localStorage.getItem(storageKey({ configName, size, mySlot }))
      if (raw) {
        const s = JSON.parse(raw) as DraftState
        setPicks(s.picks ?? [])
      } else {
        setPicks([])
      }
    } catch {
      setPicks([])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [started, configName, size, mySlot])

  // persist on every change
  useEffect(() => {
    if (!started) return
    try {
      localStorage.setItem(
        storageKey({ configName, size, mySlot }),
        JSON.stringify({ configName, size, mySlot, picks } as DraftState)
      )
    } catch {
      /* ignore quota */
    }
  }, [started, configName, size, mySlot, picks])

  const draftedIds = useMemo(() => new Set(picks.map((p) => p.id)), [picks])
  const myPlayerIds = useMemo(() => picks.filter((p) => p.slot === mySlot).map((p) => p.id), [picks, mySlot])
  const byId = useMemo(() => {
    const m = new Map<string, Player>()
    for (const p of board ?? []) m.set(p.id, p)
    return m
  }, [board])

  // total roster spots per team (starters + bench) → the draft can't run past a full board
  const slotsPerTeam = useMemo(
    () => (config ? config.roster.reduce((a, s) => a + s.count, 0) : 0),
    [config]
  )
  const maxPicks = slotsPerTeam * size
  const draftComplete = maxPicks > 0 && picks.length >= maxPicks

  const currentPick = picks.length + 1
  const onClock = slotOnClock(currentPick, size)
  const round = Math.floor((currentPick - 1) / size) + 1
  const myTurn = onClock === mySlot && !draftComplete
  const untilNext = picksUntilNext(mySlot, size, currentPick)

  const recs = useMemo(() => {
    if (!board || !config) return []
    return recommend({ board, config, draftedIds, myPlayerIds, topN: 6 })
  }, [board, config, draftedIds, myPlayerIds])

  const myPlayers = useMemo(() => myPlayerIds.map((id) => byId.get(id)).filter(Boolean) as Player[], [myPlayerIds, byId])
  const filledRoster = useMemo(() => (config ? assignRoster(myPlayers, config.roster) : []), [myPlayers, config])
  const openSlots = useMemo(() => {
    if (!config) return null
    return openStarterSlots(myPlayers.map((p) => p.pos), rosterRequirements(config.roster))
  }, [myPlayers, config])

  // positions my still-open roster slots (starters + flex + bench + K/DST) can accept — used to stop me
  // drafting a player who has nowhere to go on MY roster (e.g. a skill player when only K/DST slots remain)
  const myOpenEligibility = useMemo(() => {
    const s = new Set<string>()
    for (const fs of filledRoster) if (!fs.player) fs.eligible.forEach((e) => s.add(e))
    return s
  }, [filledRoster])
  const onlyKdstLeft =
    myOpenEligibility.size > 0 && Array.from(myOpenEligibility).every((p) => p === "K" || p === "DST")
  const canPickForMe = (pos: string) => !myTurn || myOpenEligibility.has(pos)

  const draftPlayer = useCallback(
    (id: string, pos: string) => {
      if (draftComplete) return
      if (onClock === mySlot && !myOpenEligibility.has(pos)) return // no open slot on my roster fits
      setPicks((prev) => {
        if (maxPicks > 0 && prev.length >= maxPicks) return prev // rosters full — no overflow
        if (prev.some((p) => p.id === id)) return prev // already drafted (guard double-click)
        return [...prev, { id, slot: slotOnClock(prev.length + 1, size) }]
      })
    },
    [size, maxPicks, draftComplete, onClock, mySlot, myOpenEligibility]
  )
  const undo = useCallback(() => setPicks((prev) => prev.slice(0, -1)), [])
  const resetDraft = useCallback(() => {
    if (confirm("Reset this draft? All tracked picks will be cleared.")) setPicks([])
  }, [])

  const available = useMemo(() => {
    const rows = (board ?? []).filter((p) => !draftedIds.has(p.id))
    const q = search.trim().toLowerCase()
    const filtered = rows.filter(
      (p) => (posFilter === "ALL" || p.pos === posFilter) && (!q || p.name.toLowerCase().includes(q))
    )
    // The ordering lives in the engine module beside `recommend`, so best-available and the
    // recommendations cannot disagree about K/DST. `deferLowPred` is off only when the user has
    // explicitly asked for one of those positions with the filter tabs.
    return sortAvailable(filtered, {
      sortCol,
      sortDir,
      deferLowPred: posFilter !== "K" && posFilter !== "DST",
    })
  }, [board, draftedIds, search, posFilter, sortCol, sortDir])

  const toggleSort = (col: "pts" | "vor") => {
    if (sortCol === col) setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    else { setSortCol(col); setSortDir("desc") }
  }

  // completion summary — starters filled + total projected starter points
  const starterSummary = useMemo(() => {
    const starters = filledRoster.filter((s) => !s.bench && s.player)
    const pts = starters.reduce((a, s) => a + (s.player?.pts ?? 0), 0)
    const filledStarters = filledRoster.filter((s) => !s.bench)
    return {
      startersFilled: starters.length,
      starterSlots: filledStarters.length,
      benchFilled: filledRoster.filter((s) => s.bench && s.player).length,
      projPoints: Math.round(pts),
    }
  }, [filledRoster])

  // ── SETUP screen ──────────────────────────────────────────────────────────────────────────────
  if (!started) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-10">
        <h1 className="text-2xl font-semibold text-white">Draft Optimizer</h1>
        <p className="mt-2 text-sm text-gray-400">
          Set up your league, then track picks live. When you&apos;re on the clock the optimizer
          recommends the value-maximizing pick for your roster — VOR, positional need, and tier cliffs.
        </p>
        <div className="mt-6 rounded-lg border border-[#262626] bg-[#0f0f0f] p-5">
          {manifestLoading && <p className="text-sm text-gray-500">Loading league presets…</p>}
          {manifestError && <p className="text-sm text-rose-400">Could not load the {SEASON} draft boards.</p>}
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
              <div className="grid grid-cols-2 gap-4">
                <Field label="League size">
                  {/* a saved league fixes its own size, so show that value even if the shipped
                      board sizes do not include it */}
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
                <Field label="Your draft slot">
                  <Picker
                    value={String(mySlot)}
                    onValueChange={(v) => setMySlot(Number(v))}
                    ariaLabel="My draft slot"
                    className="w-full rounded-md border border-[#262626] bg-[#0a0a0a] px-3 py-2 text-base sm:text-sm text-white"
                    options={Array.from({ length: size }, (_, i) => i + 1).map((s) => ({
                      value: String(s),
                      label: `Pick ${s}`,
                    }))}
                  />
                </Field>
              </div>
              <Button
                onClick={() => setStarted(true)}
                className="mt-2 bg-[#10b981] font-semibold text-[#0a0a0a] hover:bg-[#059669]"
              >
                Start draft
              </Button>
            </div>
          )}
        </div>
        <HonestNote />
      </div>
    )
  }

  // ── DRAFT screen ──────────────────────────────────────────────────────────────────────────────
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      {/* header / status bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#262626] bg-[#0f0f0f] px-4 py-3">
        <div className="flex items-center gap-4">
          <button onClick={() => setStarted(false)} className="text-xs text-gray-500 hover:text-gray-300">
            ← Setup
          </button>
          <div>
            <div className="text-sm font-medium text-white">{config?.label}</div>
            <div className="text-xs text-gray-500">
              {size}-team · your slot #{mySlot}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-xs text-gray-500">
              {draftComplete ? `Complete · ${picks.length}/${maxPicks} picks` : `Round ${round} · Pick ${currentPick}`}
            </div>
            <div className={`text-sm font-semibold ${myTurn ? "text-[#10b981]" : "text-white"}`}>
              {draftComplete
                ? "Draft complete"
                : myTurn
                ? "Your pick"
                : `Team #${onClock} on the clock`}
              {!myTurn && !draftComplete && untilNext > 0 && (
                <span className="ml-1 font-normal text-gray-500">· {untilNext} until you</span>
              )}
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={undo} disabled={!picks.length} className="text-gray-400 hover:text-white">
            <Undo2 className="mr-1 h-3.5 w-3.5" /> Undo
          </Button>
          <Button variant="ghost" size="sm" onClick={resetDraft} disabled={!picks.length} className="text-gray-400 hover:text-white">
            <RotateCcw className="mr-1 h-3.5 w-3.5" /> Reset
          </Button>
        </div>
      </div>

      {/* explicit turn banner — who this pick is being recorded for */}
      {!draftComplete ? (
        myTurn ? (
          <div className="mt-3 rounded-lg border border-[#10b981]/50 bg-[#10b981]/10 px-4 py-2.5 text-sm font-semibold text-[#10b981]">
            ★ Your pick — choose a player below to add to your team.
          </div>
        ) : (
          <div className="mt-3 rounded-lg border border-[#262626] bg-[#141414] px-4 py-2.5 text-sm text-gray-300">
            Recording <span className="font-semibold text-white">Team #{onClock}</span>&apos;s pick (not
            your team) — mark whoever they took.
            {untilNext > 0 && <span className="text-gray-500"> Your next pick is in {untilNext}.</span>}
          </div>
        )
      ) : (
        <div className="mt-3 rounded-lg border border-[#10b981]/50 bg-[#10b981]/10 px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-base font-semibold text-[#10b981]">🎉 Draft complete!</div>
              <div className="mt-0.5 text-sm text-gray-300">
                You filled all {maxPicks} roster spots. Review your team on the right —{" "}
                <span className="text-white">{starterSummary.startersFilled}/{starterSummary.starterSlots}</span>{" "}
                starters set,{" "}
                {/* Prose, not a column — so it takes the WORD rather than a popover. "expected"
                    is the load-bearing half: this total already prices in the chance each starter
                    misses games, so it reads low against a sum of "if everyone plays every week"
                    projections. */}
                <span className="text-white">~{starterSummary.projPoints}</span> expected starter
                points across the season.
              </div>
            </div>
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={undo} className="text-gray-300 hover:text-white">
                <Undo2 className="mr-1 h-3.5 w-3.5" /> Undo last
              </Button>
              <Button
                size="sm"
                onClick={resetDraft}
                className="bg-[#10b981] font-semibold text-[#0a0a0a] hover:bg-[#059669]"
              >
                Start a new draft
              </Button>
            </div>
          </div>
        </div>
      )}

      {boardLoading && <p className="mt-6 text-sm text-gray-500">Loading board…</p>}

      {board && config && (
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
          {/* LEFT: recommendations + available board */}
          <div className="flex flex-col gap-4">
            {/* recommendations */}
            <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
              <div className="mb-3 flex items-center gap-2">
                <h2 className="text-sm font-semibold text-white">
                  {myTurn ? "Recommended picks — your turn" : "Best available for your team"}
                </h2>
                <InfoTip label={null}>
                  Picks are ranked by <strong>VOR</strong> (Value Over Replacement — projected fantasy
                  points above the last startable player at the position), then adjusted for{" "}
                  <strong>your roster needs</strong> and <strong>positional tier cliffs</strong> (how
                  much value drops to the next player at that position if you wait). The green{" "}
                  <span className="text-[#10b981]">+</span> is the roster-need boost. Not betting advice.
                </InfoTip>
              </div>
              {myTurn && onlyKdstLeft && (
                <div className="mb-3 rounded-md border border-violet-500/30 bg-violet-500/10 px-3 py-2 text-xs text-violet-300">
                  Only K / DST slots remain — draft a Kicker or Defense from the board below (filter{" "}
                  <span className="font-semibold">K</span> or <span className="font-semibold">DST</span>).
                </div>
              )}
              <div className="flex flex-col gap-2">
                {recs.map((r, i) => (
                  <div
                    key={r.player.id}
                    className={`flex items-center gap-3 rounded-md border px-3 py-2 ${
                      i === 0 ? "border-[#10b981]/40 bg-[#10b981]/5" : "border-[#1f1f1f] bg-[#0a0a0a]"
                    }`}
                  >
                    <span className="w-5 text-center text-xs font-semibold text-gray-500">{i + 1}</span>
                    <PosBadge pos={r.player.pos} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium text-white">{r.player.name}</span>
                        <span className="text-xs text-gray-600">
                          {teamLabel(r.player)} · {r.player.pos}{r.player.posRank}
                          {r.player.bye != null && ` · ${byeLabel(r.player.bye)}`}
                        </span>
                        {r.player.rookie && <span className="rounded bg-sky-500/15 px-1 text-[10px] text-sky-300">R</span>}
                      </div>
                      <div className="truncate text-xs text-gray-500">{r.rationale}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-semibold text-white">{r.score.toFixed(0)}</div>
                      <div className="text-[10px] text-gray-600">
                        VOR {r.player.vor?.toFixed(0)}
                        {r.needBonus > 0 && <span className="text-[#10b981]"> +{r.needBonus.toFixed(0)}</span>}
                      </div>
                    </div>
                    <Button
                      size="sm"
                      onClick={() => draftPlayer(r.player.id, r.player.pos)}
                      disabled={draftComplete || !canPickForMe(r.player.pos)}
                      title={myTurn && !canPickForMe(r.player.pos) ? "No open slot on your roster fits this position" : undefined}
                      className={
                        myTurn
                          ? "bg-[#10b981] font-semibold text-[#0a0a0a] hover:bg-[#059669]"
                          : "border border-[#2a2a2a] bg-transparent font-medium text-gray-300 hover:border-[#10b981] hover:text-[#10b981]"
                      }
                    >
                      {myTurn ? "Draft" : `→ T${onClock}`}
                    </Button>
                  </div>
                ))}
                {!recs.length && <p className="text-sm text-gray-500">No players available.</p>}
              </div>
            </div>

            {/* available board / cheat sheet */}
            <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <h2 className="mr-auto text-sm font-semibold text-white">Available players</h2>
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-600" />
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search…"
                    className="w-40 rounded-md border border-[#262626] bg-[#0a0a0a] py-1.5 pl-7 pr-2 text-base sm:text-xs text-white placeholder:text-gray-600"
                  />
                </div>
                <div className="flex flex-wrap gap-1">
                  {["ALL", ...FILTER_POSITIONS].map((p) => (
                    <button
                      key={p}
                      onClick={() => setPosFilter(p)}
                      className={`rounded px-2 py-1 text-xs font-medium ${
                        posFilter === p ? "bg-[#10b981] text-[#0a0a0a]" : "bg-[#1a1a1a] text-gray-400 hover:text-white"
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
              <p className="mb-2 text-[11px] text-gray-600">
                <strong className="text-gray-500">VOR</strong> = Value Over Replacement (points above the
                last startable player at the position). K &amp; D/ST are projected too, but only as
                streaming tiers — the spread between the best and a replacement-level one is small
                next to how far either can swing, so they sit below every skill player here. Use the
                K and DST tabs to see them.
              </p>
              <div className="max-h-[520px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-[#0f0f0f] text-left text-[11px] uppercase tracking-wide text-gray-600">
                    <tr>
                      <th className="py-1.5 pl-1 font-medium">#</th>
                      <th className="py-1.5 font-medium">Player</th>
                      <th className="py-1.5 text-right font-medium">
                        <button onClick={() => toggleSort("pts")} className="hover:text-gray-300">
                          Pts{sortCol === "pts" ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                        </button>
                      </th>
                      <th className="py-1.5 text-right font-medium">
                        <button onClick={() => toggleSort("vor")} className="hover:text-gray-300">
                          VOR{sortCol === "vor" ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                        </button>
                      </th>
                      <th className="py-1.5 pr-1 text-right font-medium"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {available.slice(0, 250).map((p) => (
                      <tr key={p.id} className="border-t border-[#171717] hover:bg-[#141414]">
                        <td
                          className="py-1.5 pl-1 text-xs text-gray-600"
                          title={
                            p.lowPred
                              ? "No overall rank — K and D/ST projections are streaming tiers, not a rank comparable to skill players"
                              : undefined
                          }
                        >
                          {/* ⭐ `ovrRank` is a CROSS-POSITION rank built from VOR, and VOR is exactly
                              what is not comparable at K/DST — showing "56" here is what put a D/ST
                              level with WRs. Their POSITION rank (DST4, K2) is already beside the
                              name, so nothing is lost. It also keeps the column monotonic once these
                              rows are deferred, instead of jumping backwards at the boundary. */}
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
                            <span className="text-xs text-gray-600">
                              {teamLabel(p)}{p.posRank ? ` · ${p.pos}${p.posRank}` : ""}
                              {p.bye != null && ` · ${byeLabel(p.bye)}`}
                            </span>
                            {p.rookie && <span className="rounded bg-sky-500/15 px-1 text-[10px] text-sky-300">R</span>}
                          </div>
                        </td>
                        <td className="py-1.5 text-right text-gray-300">{p.pts != null ? p.pts.toFixed(0) : "—"}</td>
                        <td className="py-1.5 text-right text-gray-400">{p.vor != null ? p.vor.toFixed(0) : "—"}</td>
                        <td className="py-1.5 pr-1 text-right">
                          <button
                            onClick={() => draftPlayer(p.id, p.pos)}
                            disabled={draftComplete || !canPickForMe(p.pos)}
                            title={
                              myTurn && !canPickForMe(p.pos)
                                ? "No open slot on your roster fits this position"
                                : myTurn
                                ? "Draft to your team"
                                : `Record for Team #${onClock}`
                            }
                            className="rounded border border-[#2a2a2a] px-2 py-0.5 text-xs text-gray-400 hover:border-[#10b981] hover:text-[#10b981] disabled:opacity-30"
                          >
                            {myTurn ? "Draft" : `→ T${onClock}`}
                          </button>
                        </td>
                      </tr>
                    ))}
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

          {/* RIGHT: my roster + needs */}
          <div className="flex flex-col gap-4">
            <RosterPanel filled={filledRoster} openSlots={openSlots} config={config} />
            <RecentPicks picks={picks} byId={byId} mySlot={mySlot} />
          </div>
        </div>
      )}
      <HonestNote />
    </div>
  )
}

// ── sub-components ────────────────────────────────────────────────────────────────────────────────
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-gray-500">{label}</span>
      {children}
    </label>
  )
}

function PosBadge({ pos, small }: { pos: string; small?: boolean }) {
  return (
    <span
      className={`inline-flex items-center justify-center rounded border font-semibold ${
        POS_COLORS[pos] ?? "text-gray-400 bg-gray-500/10 border-gray-500/30"
      } ${small ? "h-5 w-8 text-[10px]" : "h-6 w-9 text-xs"}`}
    >
      {pos}
    </span>
  )
}

function RosterPanel({
  filled,
  openSlots,
  config,
}: {
  filled: FilledSlot[]
  openSlots: ReturnType<typeof openStarterSlots> | null
  config: LeagueConfigMeta
}) {
  const needs: string[] = []
  if (openSlots) {
    for (const [pos, n] of Object.entries(openSlots.dedicated)) {
      if (POSITIONS.includes(pos as (typeof POSITIONS)[number])) needs.push(n > 1 ? `${n}× ${pos}` : pos)
    }
    if (openSlots.flex.length) needs.push(`${openSlots.flex.length}× FLEX`)
  }
  const hasKdst = config.roster.some((s) => !s.bench && (s.eligible.includes("K") || s.eligible.includes("DST")))

  // same-position / same-bye clusters among my drafted skill players (2+ = a bye-week stack to flag)
  const byeGroups = new Map<string, { pos: string; bye: number; n: number }>()
  for (const s of filled) {
    const pl = s.player
    if (!pl || pl.bye == null || !POSITIONS.includes(pl.pos as (typeof POSITIONS)[number])) continue
    const key = `${pl.pos}|${pl.bye}`
    const g = byeGroups.get(key) ?? { pos: pl.pos, bye: pl.bye, n: 0 }
    g.n += 1
    byeGroups.set(key, g)
  }
  const byeConflicts = Array.from(byeGroups.values())
    .filter((g) => g.n >= 2)
    .sort((a, b) => b.n - a.n)
    .map((g) => `${g.n} ${g.pos} on Bye ${g.bye}`)

  return (
    <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
      <h2 className="mb-3 text-sm font-semibold text-white">Your team</h2>
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
          <div key={i} className="flex items-center gap-2 rounded border border-[#1a1a1a] bg-[#0a0a0a] px-2 py-1.5">
            <span className="w-12 text-[11px] font-medium uppercase text-gray-500">{s.slotName}</span>
            {s.player ? (
              <>
                <PosBadge pos={s.player.pos} small />
                <span className="truncate text-sm text-white">{s.player.name}</span>
                {s.player.bye != null && <span className="text-[10px] text-gray-600">Bye {s.player.bye}</span>}
                <span className="ml-auto text-xs text-gray-600">{s.player.vor != null ? s.player.vor.toFixed(0) : "—"}</span>
              </>
            ) : (
              <span className="text-xs text-gray-700">empty</span>
            )}
          </div>
        ))}
      </div>
      {byeConflicts.length > 0 && (
        <div className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 py-2 text-[11px] leading-snug text-amber-300">
          ⚠ Bye-week stack: {byeConflicts.join(", ")}. You&apos;d have multiple starters idle the same week.
        </div>
      )}
      {hasKdst && (
        <p className="mt-3 text-[11px] leading-snug text-gray-600">
          K &amp; DST are projected, but only as streaming tiers rather than precise ranks — so they
          sit below the skill players on the board (use the K and DST tabs), and the optimizer holds
          them back until your roster needs them. Expect them in your last picks.
        </p>
      )}
    </div>
  )
}

function RecentPicks({ picks, byId, mySlot }: { picks: Pick[]; byId: Map<string, Player>; mySlot: number }) {
  if (!picks.length) return null
  const recent = [...picks].slice(-12).reverse()
  return (
    <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
      <h2 className="mb-2 text-sm font-semibold text-white">Recent picks</h2>
      <div className="flex flex-col gap-1">
        {recent.map((p, i) => {
          const player = byId.get(p.id)
          const overall = picks.length - i
          return (
            <div key={`${p.id}-${overall}`} className="flex items-center gap-2 text-xs">
              <span className="w-8 text-gray-600">#{overall}</span>
              <span className={p.slot === mySlot ? "font-medium text-[#10b981]" : "text-gray-400"}>
                T{p.slot}
              </span>
              {player && <PosBadge pos={player.pos} small />}
              <span className="truncate text-gray-300">{player?.name ?? p.id}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function HonestNote() {
  return (
    <p className="mx-auto mt-8 max-w-3xl text-center text-[11px] leading-relaxed text-gray-600">
      Projections are a first-pass model (NF-FASTPATH → NF-C1): point ranks are trustworthy; the VOR
      interval is a first-order estimate, not yet calibrated. This is analysis, not betting advice.
    </p>
  )
}
