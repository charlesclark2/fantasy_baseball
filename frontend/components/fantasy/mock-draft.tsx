"use client"

// The MOCK DRAFT simulator (NF-C2.1). The live tool (MVP-3) tracks a draft that is happening to
// you; this one runs a whole draft against CPU opponents so you can practise a slot, try a strategy
// twice from the same seed, or just draft in June.
//
// ⭐ WHAT IS REUSED vs WHAT IS NEW. The board, the recommendation engine (`recommend`), the roster
// assignment and the snake arithmetic are all the SAME modules the live optimizer uses — a mock
// draft that recommended differently from the real tool would be practice for a product that does
// not exist. The net-new is the opponents (`lib/mock-draft`: seeded personas blending market ADP
// with our own board) and the loop that runs them, plus the post-draft grade.
//
// Honest framing (best_alpha = 0): the recommendations reason off OUR projections and VOR and say
// why, and the grade scores the room on those same projections — a circular measure, labelled as
// one on the screen (`GRADE_CIRCULARITY_NOTE`). Nothing here claims an edge over the market or a
// season outcome.

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import { FastForward, RotateCcw, Search, Undo2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Picker } from "@/components/ui/picker"
import { InfoTip } from "@/components/fantasy/shared"
import {
  assignRoster,
  openStarterSlots,
  recommend,
  rosterRequirements,
  slotOnClock,
  sortAvailable,
  type FilledSlot,
  type LeagueConfigMeta,
  type Player,
} from "@/lib/draft-optimizer"
import {
  GRADE_CIRCULARITY_NOTE,
  boardOrder,
  gradeDraft,
  marketDepth,
  marketOrder,
  personaFor,
  randomSeed,
  simulateCpuPicks,
  type CpuChoice,
  type DraftGrade,
  type Pick,
} from "@/lib/mock-draft"
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
/** The positions the roster panel lists as a NEED — skill only; see the note in `RosterPanel`. */
const NEED_POSITIONS: string[] = ["QB", "RB", "WR", "TE"]

/** Quick = the rounds people actually want to rehearse; Full = the whole roster. */
const QUICK_ROUNDS = 8

/** CPU reveal pacing. A mock draft with no pause at all is a wall of text you cannot read, and one
 *  that waits like a real room is unusable in a browser tab — so both are offered and neither is
 *  the only way through: "Skip to my pick" resolves the identical picks instantly (the sim is
 *  seeded per pick, so fast-forwarding cannot change the draft). */
const SPEEDS = { fast: 70, realistic: 500 } as const
type SpeedKey = keyof typeof SPEEDS

const teamLabel = (p: { team: string | null; rookie: boolean }) => p.team ?? (p.rookie ? "Rk" : "FA")

interface MockState {
  configName: string
  size: number
  mySlot: number
  rounds: number
  seed: number
  picks: Pick[]
}

const storageKey = (s: { configName: string; size: number; mySlot: number }) =>
  `nfl-mock-draft-${SEASON}-${s.configName}-${s.size}-slot${s.mySlot}`

export function MockDraft() {
  const { data: manifest, isLoading: manifestLoading, error: manifestError } = useFantasyManifest()
  const { data: savedLeagues } = useSavedLeagues()

  const [started, setStarted] = useState(false)
  const [configName, setConfigName] = useState<string>("")
  const [size, setSize] = useState<number>(12)
  const [mySlot, setMySlot] = useState<number>(1)
  const [quick, setQuick] = useState(true)
  const [speed, setSpeed] = useState<SpeedKey>("fast")
  const [seed, setSeed] = useState<number>(1)
  const [picks, setPicks] = useState<Pick[]>([])
  const [log, setLog] = useState<Record<string, string>>({}) // playerId -> the CPU's stated reason
  const [search, setSearch] = useState("")
  const [posFilter, setPosFilter] = useState<string>("ALL")

  // A seed is chosen on the CLIENT after mount — `Math.random()` during render would differ between
  // the server and the client pass and trip hydration.
  useEffect(() => {
    setSeed((s) => (s === 1 ? randomSeed() : s))
  }, [])

  useEffect(() => {
    if (manifest && !configName) {
      setConfigName(manifest.configs.find((c) => c.name === "half_ppr")?.name ?? manifest.configs[0]?.name ?? "")
      setSize(manifest.sizes.includes(12) ? 12 : manifest.sizes[0])
    }
  }, [manifest, configName])

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
      setMySlot((s) => Math.min(s, selectedLeague.n_teams))
    }
  }, [selectedLeague, size])

  const { board, isLoading: boardLoading } = useResolvedBoard(
    started ? configName : null,
    started ? size : null,
  )

  // The two ranking orders the CPU blends, and our own board order. Both are pure functions of the
  // board, so they are computed once per board rather than per pick.
  const market = useMemo(() => (board ? marketOrder(board) : new Map<string, number>()), [board])
  const brdOrder = useMemo(() => (board ? boardOrder(board) : new Map<string, number>()), [board])
  const adpDepth = useMemo(() => (board ? marketDepth(board) : 0), [board])

  const slotsPerTeam = useMemo(
    () => (config ? config.roster.reduce((a, s) => a + s.count, 0) : 0),
    [config],
  )
  const rounds = quick ? Math.min(QUICK_ROUNDS, slotsPerTeam) : slotsPerTeam
  const maxPicks = rounds * size

  // restore an in-progress mock for this exact (config, size, slot)
  useEffect(() => {
    if (!started) return
    try {
      const raw = localStorage.getItem(storageKey({ configName, size, mySlot }))
      if (raw) {
        const s = JSON.parse(raw) as MockState
        setPicks(s.picks ?? [])
        if (typeof s.seed === "number") setSeed(s.seed)
      } else {
        setPicks([])
      }
    } catch {
      setPicks([])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [started, configName, size, mySlot])

  useEffect(() => {
    if (!started) return
    try {
      localStorage.setItem(
        storageKey({ configName, size, mySlot }),
        JSON.stringify({ configName, size, mySlot, rounds, seed, picks } as MockState),
      )
    } catch {
      /* ignore quota */
    }
  }, [started, configName, size, mySlot, rounds, seed, picks])

  const draftedIds = useMemo(() => new Set(picks.map((p) => p.id)), [picks])
  const myPlayerIds = useMemo(() => picks.filter((p) => p.slot === mySlot).map((p) => p.id), [picks, mySlot])
  const byId = useMemo(() => {
    const m = new Map<string, Player>()
    for (const p of board ?? []) m.set(p.id, p)
    return m
  }, [board])

  const draftComplete = maxPicks > 0 && picks.length >= maxPicks
  const currentPick = picks.length + 1
  const onClock = slotOnClock(currentPick, size)
  const round = Math.floor((currentPick - 1) / size) + 1
  const myTurn = onClock === mySlot && !draftComplete

  const simArgs = useMemo(
    () =>
      board && config
        ? { board, config, nTeams: size, mySlot, seed, maxPicks, market, boardRank: brdOrder }
        : null,
    [board, config, size, mySlot, seed, maxPicks, market, brdOrder],
  )

  // ⭐ THE LIVE PICK LIST, MIRRORED INTO A REF. `runCpu` fires from a timer, from a click, and
  // (in development) twice per effect under StrictMode, so it must read the CURRENT picks rather
  // than whatever its render closed over — and it must be safe to call twice in a row.
  //
  // ⚠️ NOT a `setPicks` functional updater, which is the obvious way to get the same freshness:
  // this call also has to record the CPU's stated reasons, and a `setState` nested inside another
  // updater is a side effect in a function React requires to be pure (it is re-invoked under
  // StrictMode, so the log would be written twice). Advancing the ref synchronously gives the same
  // idempotence with no impure updater.
  const picksRef = useRef<Pick[]>(picks)
  useEffect(() => {
    picksRef.current = picks
  }, [picks])

  /** Append CPU picks. `limit` unset ⇒ run all the way to the user's next turn. */
  const runCpu = useCallback(
    (limit?: number) => {
      if (!simArgs) return
      const prev = picksRef.current
      if (prev.length >= maxPicks) return
      if (slotOnClock(prev.length + 1, size) === mySlot) return
      const { picks: added, choices } = simulateCpuPicks({ ...simArgs, picks: prev, limit })
      if (!added.length) return
      picksRef.current = [...prev, ...added]
      setPicks(picksRef.current)
      setLog((l) => {
        const next = { ...l }
        choices.forEach((c: CpuChoice) => (next[c.player.id] = c.reason))
        return next
      })
    },
    [simArgs, maxPicks, size, mySlot],
  )

  // ── the sim loop ──────────────────────────────────────────────────────────────────────────────
  // One CPU pick per tick while it is not the user's turn. Keyed on `picks.length` so each landed
  // pick schedules the next; the cleanup cancels an in-flight tick on unmount or on a manual skip.
  const delay = SPEEDS[speed]
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (!started || !simArgs || draftComplete || myTurn) return
    timer.current = setTimeout(() => runCpu(1), delay)
    return () => {
      if (timer.current) clearTimeout(timer.current)
    }
  }, [started, simArgs, draftComplete, myTurn, picks.length, delay, runCpu])

  const draftPlayer = useCallback(
    (id: string) => {
      if (!myTurn) return
      setPicks((prev) => {
        if (maxPicks > 0 && prev.length >= maxPicks) return prev
        if (prev.some((p) => p.id === id)) return prev
        if (slotOnClock(prev.length + 1, size) !== mySlot) return prev
        return [...prev, { id, slot: mySlot }]
      })
    },
    [myTurn, maxPicks, size, mySlot],
  )

  const undo = useCallback(() => {
    // Rewind to just before the user's own last pick — undoing one CPU pick at a time would be
    // meaningless (the very next tick makes it again, identically, because the sim is seeded).
    setPicks((prev) => {
      const lastMine = prev.map((p) => p.slot).lastIndexOf(mySlot)
      return lastMine === -1 ? [] : prev.slice(0, lastMine)
    })
  }, [mySlot])

  const restart = useCallback(() => {
    setPicks([])
    setLog({})
    setSeed(randomSeed())
  }, [])

  const recs = useMemo(() => {
    if (!board || !config) return []
    return recommend({ board, config, draftedIds, myPlayerIds, topN: 6 })
  }, [board, config, draftedIds, myPlayerIds])

  const myPlayers = useMemo(
    () => myPlayerIds.map((id) => byId.get(id)).filter(Boolean) as Player[],
    [myPlayerIds, byId],
  )
  const filledRoster = useMemo(() => (config ? assignRoster(myPlayers, config.roster) : []), [myPlayers, config])
  const openSlots = useMemo(() => {
    if (!config) return null
    return openStarterSlots(myPlayers.map((p) => p.pos), rosterRequirements(config.roster))
  }, [myPlayers, config])
  const myOpenEligibility = useMemo(() => {
    const s = new Set<string>()
    for (const fs of filledRoster) if (!fs.player) fs.eligible.forEach((e) => s.add(e))
    return s
  }, [filledRoster])
  const canPickForMe = (pos: string) => myTurn && myOpenEligibility.has(pos)

  const grade: DraftGrade | null = useMemo(() => {
    if (!board || !config || !draftComplete) return null
    return gradeDraft({ board, config, picks, nTeams: size, mySlot, market })
  }, [board, config, draftComplete, picks, size, mySlot, market])

  const available = useMemo(() => {
    const rows = (board ?? []).filter((p) => !draftedIds.has(p.id))
    const q = search.trim().toLowerCase()
    const filtered = rows.filter(
      (p) => (posFilter === "ALL" || p.pos === posFilter) && (!q || p.name.toLowerCase().includes(q)),
    )
    return sortAvailable(filtered, {
      sortCol: "ovrRank",
      sortDir: "asc",
      deferLowPred: posFilter !== "K" && posFilter !== "DST",
    })
  }, [board, draftedIds, search, posFilter])

  // ── SETUP ─────────────────────────────────────────────────────────────────────────────────────
  if (!started) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-10">
        <h1 className="text-2xl font-semibold text-white">Mock Draft</h1>
        <p className="mt-2 text-sm text-gray-400">
          Practise a full draft against CPU opponents. They pick off market ADP blended with our
          projections — each seat with its own habits — while you draft with the same recommendations
          the live optimizer gives you, and see how the room graded out at the end.
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
                <p className="mt-1 text-xs text-gray-500">{config.description}</p>
              </Field>
              <div className="grid grid-cols-2 gap-4">
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
              <div className="grid grid-cols-2 gap-4">
                <Field label="Draft length">
                  <Picker
                    value={quick ? "quick" : "full"}
                    onValueChange={(v) => setQuick(v === "quick")}
                    ariaLabel="Draft length"
                    className="w-full rounded-md border border-[#262626] bg-[#0a0a0a] px-3 py-2 text-base sm:text-sm text-white"
                    options={[
                      { value: "quick", label: `Quick — ${Math.min(QUICK_ROUNDS, slotsPerTeam)} rounds` },
                      { value: "full", label: `Full roster — ${slotsPerTeam} rounds` },
                    ]}
                  />
                </Field>
                <Field label="Opponent pace">
                  <Picker
                    value={speed}
                    onValueChange={(v) => setSpeed(v as SpeedKey)}
                    ariaLabel="Opponent pace"
                    className="w-full rounded-md border border-[#262626] bg-[#0a0a0a] px-3 py-2 text-base sm:text-sm text-white"
                    options={[
                      { value: "fast", label: "Fast" },
                      { value: "realistic", label: "Realistic" },
                    ]}
                  />
                </Field>
              </div>
              <Button
                onClick={() => setStarted(true)}
                className="mt-2 bg-[#10b981] font-semibold text-[#0a0a0a] hover:bg-[#059669]"
              >
                Start mock draft
              </Button>
            </div>
          )}
        </div>
        <HonestNote />
      </div>
    )
  }

  // ── DRAFT ─────────────────────────────────────────────────────────────────────────────────────
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#262626] bg-[#0f0f0f] px-4 py-3">
        <div className="flex items-center gap-4">
          <button onClick={() => setStarted(false)} className="text-xs text-gray-500 hover:text-gray-300">
            ← Setup
          </button>
          <div>
            <div className="text-sm font-medium text-white">{config?.label}</div>
            <div className="text-xs text-gray-500">
              Mock · {size}-team · your slot #{mySlot} · {rounds} rounds
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-xs text-gray-500">
              {draftComplete ? `Complete · ${picks.length}/${maxPicks} picks` : `Round ${round} · Pick ${currentPick}`}
            </div>
            <div className={`text-sm font-semibold ${myTurn ? "text-[#10b981]" : "text-white"}`}>
              {draftComplete ? "Mock complete" : myTurn ? "You're on the clock" : `Team ${onClock} is picking…`}
            </div>
          </div>
          {!draftComplete && !myTurn && (
            <Button
              size="sm"
              onClick={() => runCpu()}
              className="bg-[#1f2937] font-medium text-gray-200 hover:bg-[#374151]"
            >
              <FastForward className="mr-1 h-3.5 w-3.5" /> Skip to my pick
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={undo}
            disabled={!myPlayerIds.length}
            className="text-gray-400 hover:text-white"
          >
            <Undo2 className="mr-1 h-3.5 w-3.5" /> Undo my pick
          </Button>
          <Button variant="ghost" size="sm" onClick={restart} className="text-gray-400 hover:text-white">
            <RotateCcw className="mr-1 h-3.5 w-3.5" /> New room
          </Button>
        </div>
      </div>

      {!draftComplete && (
        <div
          className={`mt-3 rounded-lg border px-4 py-2.5 text-sm ${
            myTurn
              ? "border-[#10b981]/50 bg-[#10b981]/10 font-semibold text-[#10b981]"
              : "border-[#262626] bg-[#141414] text-gray-300"
          }`}
        >
          {myTurn ? (
            <>★ Your pick — take one of the recommendations below, or anyone off the board.</>
          ) : (
            <>
              <span className="font-semibold text-white">Team {onClock}</span> is on the clock —{" "}
              <span className="text-gray-400">{personaFor(seed, onClock).label}</span>. Their pick lands in a
              moment, or skip ahead.
            </>
          )}
        </div>
      )}

      {boardLoading && <p className="mt-6 text-sm text-gray-500">Loading board…</p>}

      {board && config && (
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
          <div className="flex flex-col gap-4">
            {grade ? (
              <GradeCard grade={grade} rounds={rounds} slotsPerTeam={slotsPerTeam} onRestart={restart} />
            ) : (
              <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
                <div className="mb-3 flex items-center gap-2">
                  <h2 className="text-sm font-semibold text-white">
                    {myTurn ? "Recommended picks — your turn" : "Best available for your team"}
                  </h2>
                  <InfoTip label={null}>
                    Picks are ranked by <strong>VOR</strong> (Value Over Replacement — projected fantasy
                    points above the last startable player at the position), then adjusted for{" "}
                    <strong>your roster needs</strong> and <strong>positional tier cliffs</strong>. The same
                    engine the live Draft Optimizer uses. Not betting advice.
                  </InfoTip>
                </div>
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
                            {teamLabel(r.player)} · {r.player.pos}
                            {r.player.posRank}
                            {r.player.adp != null && ` · ADP ${r.player.adp.toFixed(0)}`}
                          </span>
                        </div>
                        <div className="truncate text-xs text-gray-500">{r.rationale}</div>
                      </div>
                      <div className="text-right">
                        <div className="text-sm font-semibold text-white">{r.score.toFixed(0)}</div>
                        <div className="text-[10px] text-gray-600">VOR {r.player.vor?.toFixed(0)}</div>
                      </div>
                      <Button
                        size="sm"
                        onClick={() => draftPlayer(r.player.id)}
                        disabled={!canPickForMe(r.player.pos)}
                        title={
                          myTurn && !myOpenEligibility.has(r.player.pos)
                            ? "No open slot on your roster fits this position"
                            : undefined
                        }
                        className="bg-[#10b981] font-semibold text-[#0a0a0a] hover:bg-[#059669] disabled:opacity-40"
                      >
                        Draft
                      </Button>
                    </div>
                  ))}
                  {!recs.length && <p className="text-sm text-gray-500">No players available.</p>}
                </div>
              </div>
            )}

            {/* available board */}
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
              <div className="max-h-[460px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-[#0f0f0f] text-left text-[11px] uppercase tracking-wide text-gray-600">
                    <tr>
                      <th className="py-1.5 pl-1 font-medium">#</th>
                      <th className="py-1.5 font-medium">Player</th>
                      <th className="py-1.5 text-right font-medium">ADP</th>
                      <th className="py-1.5 text-right font-medium">Pts</th>
                      <th className="py-1.5 text-right font-medium">VOR</th>
                      <th className="py-1.5 pr-1 text-right font-medium"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {available.slice(0, 200).map((p) => (
                      <tr key={p.id} className="border-t border-[#171717] hover:bg-[#141414]">
                        <td className="py-1.5 pl-1 text-xs text-gray-600">{p.lowPred ? "—" : p.ovrRank}</td>
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
                              {teamLabel(p)}
                              {p.posRank ? ` · ${p.pos}${p.posRank}` : ""}
                            </span>
                          </div>
                        </td>
                        <td className="py-1.5 text-right text-gray-500">
                          {p.adp != null ? p.adp.toFixed(0) : "—"}
                        </td>
                        <td className="py-1.5 text-right text-gray-300">{p.pts != null ? p.pts.toFixed(0) : "—"}</td>
                        <td className="py-1.5 text-right text-gray-400">{p.vor != null ? p.vor.toFixed(0) : "—"}</td>
                        <td className="py-1.5 pr-1 text-right">
                          <button
                            onClick={() => draftPlayer(p.id)}
                            disabled={!canPickForMe(p.pos)}
                            title={
                              !myTurn
                                ? "Wait for your pick"
                                : !myOpenEligibility.has(p.pos)
                                  ? "No open slot on your roster fits this position"
                                  : "Draft to your team"
                            }
                            className="rounded border border-[#2a2a2a] px-2 py-0.5 text-xs text-gray-400 hover:border-[#10b981] hover:text-[#10b981] disabled:opacity-30"
                          >
                            Draft
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-[11px] text-gray-600">
                ADP is the market&apos;s average draft position for this format — a reference column, never
                an input to the recommendations. {adpDepth} of {board.length}{" "}
                players are inside that sample; the rest are shown with &ldquo;—&rdquo; because the
                sample never drafted them.
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-4">
            <RosterPanel filled={filledRoster} openSlots={openSlots} config={config} />
            <PickLog picks={picks} byId={byId} mySlot={mySlot} log={log} size={size} />
          </div>
        </div>
      )}
      <HonestNote />
    </div>
  )
}

// ── sub-components ──────────────────────────────────────────────────────────────────────────────
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
  const hasKdst = config.roster.some(
    (s) => !s.bench && (s.eligible.includes("K") || s.eligible.includes("DST")),
  )
  // ⚠️ SKILL POSITIONS ONLY, exactly as the live optimizer's panel does it. An open K or D/ST slot
  // is technically a need from round 1 and is never one a drafter should act on — listing it beside
  // "2× RB" invites the early kicker the recommendation engine deliberately defers. The note at the
  // bottom of this panel is where K/DST are explained instead.
  const needs: string[] = []
  if (openSlots) {
    for (const [pos, n] of Object.entries(openSlots.dedicated)) {
      if (!NEED_POSITIONS.includes(pos)) continue
      needs.push(n > 1 ? `${n}× ${pos}` : pos)
    }
    if (openSlots.flex.length) needs.push(`${openSlots.flex.length}× FLEX`)
  }
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
                <span className="ml-auto text-xs text-gray-600">
                  {s.player.vor != null ? s.player.vor.toFixed(0) : "—"}
                </span>
              </>
            ) : (
              <span className="text-xs text-gray-700">empty</span>
            )}
          </div>
        ))}
      </div>
      {hasKdst && (
        <p className="mt-3 text-[11px] leading-snug text-gray-600">
          K &amp; DST are projected too, but only as streaming tiers rather than precise ranks — so
          they are not listed as a need above, they sit below the skill players on the board, and the
          optimizer holds them back until your roster requires them. Expect them in your last picks.
        </p>
      )}
    </div>
  )
}

/** The room's picks, newest first — the CPU's stated reason beside each, so an opponent's pick is
 *  legible rather than magic. */
function PickLog({
  picks,
  byId,
  mySlot,
  log,
  size,
}: {
  picks: Pick[]
  byId: Map<string, Player>
  mySlot: number
  log: Record<string, string>
  size: number
}) {
  if (!picks.length) return null
  const recent = picks.map((p, i) => ({ ...p, overall: i + 1 })).slice(-14).reverse()
  return (
    <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
      <h2 className="mb-2 text-sm font-semibold text-white">Draft log</h2>
      <div className="flex flex-col gap-1.5">
        {recent.map((p) => {
          const player = byId.get(p.id)
          const round = Math.floor((p.overall - 1) / size) + 1
          return (
            <div key={`${p.id}-${p.overall}`} className="text-xs">
              <div className="flex items-center gap-2">
                <span className="w-10 shrink-0 text-gray-600">
                  {round}.{String(((p.overall - 1) % size) + 1).padStart(2, "0")}
                </span>
                <span className={p.slot === mySlot ? "font-medium text-[#10b981]" : "text-gray-500"}>
                  {p.slot === mySlot ? "You" : `T${p.slot}`}
                </span>
                {player && <PosBadge pos={player.pos} small />}
                <span className="truncate text-gray-300">{player?.name ?? p.id}</span>
              </div>
              {p.slot !== mySlot && log[p.id] && (
                <div className="ml-12 truncate text-[10px] text-gray-600">{log[p.id]}</div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function GradeCard({
  grade,
  rounds,
  slotsPerTeam,
  onRestart,
}: {
  grade: DraftGrade
  rounds: number
  slotsPerTeam: number
  onRestart: () => void
}) {
  const { me, myRank, nTeams, roomMedian, positions, steals, reaches } = grade
  const vsMedian = me.starterPoints - roomMedian
  return (
    <div className="rounded-lg border border-[#10b981]/40 bg-[#10b981]/5 p-4" data-testid="mock-draft-grade">
      <h2 className="text-base font-semibold text-[#10b981]">Mock complete — how the room graded out</h2>

      {/* ⭐ THE RANK NAMES ITS OWN MEASURE IN THE SAME BREATH. A bare "3rd of 12" is read as a
          projected finish; this one can only be read as what it is. */}
      <p className="mt-2 text-sm text-gray-200">
        Your starters project{" "}
        <span className="font-semibold text-white">{me.starterPoints.toLocaleString()}</span> points —{" "}
        <span className="font-semibold text-white">
          {ordinal(myRank)} of {nTeams}
        </span>{" "}
        in this mock room on projected starter points, {vsMedian >= 0 ? "+" : ""}
        {vsMedian.toLocaleString()} against the room median. You filled {me.startersFilled} of{" "}
        {me.starterSlots} starter slots
        {rounds < slotsPerTeam ? ` over ${rounds} of this roster's ${slotsPerTeam} rounds` : ""}.
      </p>

      {/* ⚠️ NOT OPTIONAL, AND NOT BEHIND A CLICK — see GRADE_CIRCULARITY_NOTE. */}
      <p className="mt-2 rounded-md border border-[#262626] bg-[#0a0a0a] px-3 py-2 text-[11px] leading-relaxed text-gray-400">
        {GRADE_CIRCULARITY_NOTE}
      </p>

      <div className="mt-3">
        <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500">
          Your starters vs the room median, by position
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {/* A position NOBODY in the room has drafted yet is not a comparison — in a quick mock
              that is every K and D/ST, and rendering "K 0 (+0)" in the same green as a real edge
              says we measured something when we measured nothing. */}
          {positions
            .filter((p) => p.mine > 0 || p.roomMedian > 0)
            .map((p) => {
              const d = p.mine - p.roomMedian
              return (
                <span
                  key={p.pos}
                  className={`rounded border px-2 py-1 text-xs ${
                    d >= 0
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                      : "border-amber-500/30 bg-amber-500/10 text-amber-300"
                  }`}
                >
                  {p.pos} {p.mine.toLocaleString()}{" "}
                  <span className="opacity-70">
                    ({d >= 0 ? "+" : ""}
                    {d})
                  </span>
                </span>
              )
            })}
        </div>
      </div>

      {(steals.length > 0 || reaches.length > 0) && (
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <PickValueList
            title="Fell furthest past ADP"
            note="Still on the board later than the market average says he goes."
            rows={steals}
          />
          <PickValueList
            title="Taken earliest vs ADP"
            note="Taken before the market average says he goes."
            rows={reaches}
          />
        </div>
      )}

      <div className="mt-4 flex gap-2">
        <Button size="sm" onClick={onRestart} className="bg-[#10b981] font-semibold text-[#0a0a0a] hover:bg-[#059669]">
          Draft a new room
        </Button>
      </div>
    </div>
  )
}

function PickValueList({
  title,
  note,
  rows,
}: {
  title: string
  note: string
  rows: DraftGrade["steals"]
}) {
  if (!rows.length) return null
  return (
    <div className="rounded-md border border-[#262626] bg-[#0a0a0a] p-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">{title}</h3>
      <p className="mt-0.5 text-[10px] text-gray-600">{note}</p>
      <div className="mt-1.5 flex flex-col gap-1">
        {rows.map((r) => (
          <div key={r.player.id} className="flex items-center gap-2 text-xs">
            <PosBadge pos={r.player.pos} small />
            <span className="truncate text-gray-200">{r.player.name}</span>
            <span className="ml-auto shrink-0 text-gray-500">
              #{r.overallPick} · ADP {r.marketRank}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

const ordinal = (n: number): string => {
  const s = ["th", "st", "nd", "rd"]
  const v = n % 100
  return n + (s[(v - 20) % 10] ?? s[v] ?? s[0])
}

function HonestNote() {
  return (
    <p className="mx-auto mt-8 max-w-3xl text-center text-[11px] leading-relaxed text-gray-600">
      A mock draft is practice, not a forecast. The CPU opponents are seeded simulations of a draft
      room, not real drafters, and the projections behind every number are a first-pass model
      (NF-FASTPATH → NF-C1): point ranks are trustworthy; the VOR interval is a first-order estimate,
      not yet calibrated. This is analysis, not betting advice.
    </p>
  )
}
