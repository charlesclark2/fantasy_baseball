"use client"

// The live NFL-fantasy draft optimizer (NF-C2 / MVP-3). All client-side: the (config, size) board JSON
// loads once, then every pick recomputes recommendations instantly (no server round-trip) — fast enough
// for a live draft. A manual draft tracker records picks in snake order; when you're on the clock the
// optimizer surfaces the value-maximizing pick given your roster needs + positional scarcity (VONA /
// tier cliffs), with honest uncertainty. Pre-draft it doubles as a tiered cheat sheet.
//
// Honest framing: this is a PROJECTION product (NF-FASTPATH → NF-C1). Ranks are trustworthy; the VOR
// interval is a first-order estimate (not yet calibrated) and K/DST carry no projection.

import { useCallback, useEffect, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { RotateCcw, Undo2, Info, Search } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  recommend,
  rosterRequirements,
  openStarterSlots,
  picksUntilNext,
  slotOnClock,
  type Player,
  type LeagueConfigMeta,
  type Manifest,
  type RosterSlotDef,
} from "@/lib/draft-optimizer"

const SEASON = 2026
const POS_COLORS: Record<string, string> = {
  QB: "text-rose-400 bg-rose-500/10 border-rose-500/30",
  RB: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  WR: "text-sky-400 bg-sky-500/10 border-sky-500/30",
  TE: "text-amber-400 bg-amber-500/10 border-amber-500/30",
}
const POSITIONS = ["QB", "RB", "WR", "TE"] as const

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
function useManifest() {
  return useQuery<Manifest>({
    queryKey: ["nfl-fantasy-manifest", SEASON],
    queryFn: async () => {
      const r = await fetch(`/data/nfl-fantasy/${SEASON}/manifest.json`)
      if (!r.ok) throw new Error("manifest not found")
      return r.json()
    },
    staleTime: Infinity,
  })
}

function useBoard(configName: string | null, size: number | null) {
  return useQuery<Player[]>({
    queryKey: ["nfl-fantasy-board", SEASON, configName, size],
    enabled: !!configName && !!size,
    queryFn: async () => {
      const r = await fetch(`/data/nfl-fantasy/${SEASON}/board_${configName}_${size}.json`)
      if (!r.ok) throw new Error("board not found")
      return r.json()
    },
    staleTime: Infinity,
  })
}

// ── roster assignment for the "My Team" panel ───────────────────────────────────────────────────
interface FilledSlot {
  slotName: string
  eligible: string[]
  player: Player | null
  bench: boolean
}

function assignRoster(myPlayers: Player[], roster: RosterSlotDef[]): FilledSlot[] {
  const pool = [...myPlayers].sort((a, b) => (b.vor ?? 0) - (a.vor ?? 0))
  const used = new Set<string>()
  const out: FilledSlot[] = []
  // expand slots: dedicated (1 eligible) first, then flex (by eligibility size), then bench
  const starters = roster.filter((s) => !s.bench)
  const dedicated = starters.filter((s) => s.eligible.length === 1)
  const flex = starters.filter((s) => s.eligible.length > 1).sort((a, b) => a.eligible.length - b.eligible.length)
  const take = (eligible: string[]): Player | null => {
    for (const p of pool) {
      if (!used.has(p.id) && eligible.includes(p.pos)) {
        used.add(p.id)
        return p
      }
    }
    return null
  }
  for (const grp of [dedicated, flex]) {
    for (const s of grp) {
      for (let i = 0; i < s.count; i++) {
        out.push({ slotName: s.name, eligible: s.eligible, player: take(s.eligible), bench: false })
      }
    }
  }
  // leftovers → bench rows
  const bench = roster.filter((s) => s.bench).reduce((a, s) => a + s.count, 0)
  const leftover = pool.filter((p) => !used.has(p.id))
  for (let i = 0; i < Math.max(bench, leftover.length); i++) {
    out.push({ slotName: "BN", eligible: [], player: leftover[i] ?? null, bench: true })
  }
  return out
}

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

  // default the config once the manifest lands
  useEffect(() => {
    if (manifest && !configName) {
      setConfigName(manifest.configs.find((c) => c.name === "half_ppr")?.name ?? manifest.configs[0]?.name ?? "")
      setSize(manifest.sizes.includes(12) ? 12 : manifest.sizes[0])
    }
  }, [manifest, configName])

  const config: LeagueConfigMeta | undefined = manifest?.configs.find((c) => c.name === configName)
  const { data: board, isLoading: boardLoading } = useBoard(started ? configName : null, started ? size : null)

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

  const currentPick = picks.length + 1
  const onClock = slotOnClock(currentPick, size)
  const round = Math.floor((currentPick - 1) / size) + 1
  const myTurn = onClock === mySlot
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

  const draftPlayer = useCallback(
    (id: string) => setPicks((prev) => [...prev, { id, slot: slotOnClock(prev.length + 1, size) }]),
    [size]
  )
  const undo = useCallback(() => setPicks((prev) => prev.slice(0, -1)), [])
  const resetDraft = useCallback(() => {
    if (confirm("Reset this draft? All tracked picks will be cleared.")) setPicks([])
  }, [])

  const available = useMemo(() => {
    const rows = (board ?? []).filter((p) => !draftedIds.has(p.id))
    const q = search.trim().toLowerCase()
    return rows.filter(
      (p) => (posFilter === "ALL" || p.pos === posFilter) && (!q || p.name.toLowerCase().includes(q))
    )
  }, [board, draftedIds, search, posFilter])

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
                <select
                  value={configName}
                  onChange={(e) => setConfigName(e.target.value)}
                  className="w-full rounded-md border border-[#262626] bg-[#0a0a0a] px-3 py-2 text-sm text-white"
                >
                  {manifest.configs.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.label}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-gray-500">{config.description}</p>
              </Field>
              <div className="grid grid-cols-2 gap-4">
                <Field label="League size">
                  <select
                    value={size}
                    onChange={(e) => setSize(Number(e.target.value))}
                    className="w-full rounded-md border border-[#262626] bg-[#0a0a0a] px-3 py-2 text-sm text-white"
                  >
                    {manifest.sizes.map((s) => (
                      <option key={s} value={s}>
                        {s} teams
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Your draft slot">
                  <select
                    value={mySlot}
                    onChange={(e) => setMySlot(Number(e.target.value))}
                    className="w-full rounded-md border border-[#262626] bg-[#0a0a0a] px-3 py-2 text-sm text-white"
                  >
                    {Array.from({ length: size }, (_, i) => i + 1).map((s) => (
                      <option key={s} value={s}>
                        Pick {s}
                      </option>
                    ))}
                  </select>
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
            <div className="text-xs text-gray-500">Round {round} · Pick {currentPick}</div>
            <div className={`text-sm font-semibold ${myTurn ? "text-[#10b981]" : "text-white"}`}>
              {myTurn ? "You're on the clock" : `Team #${onClock} on the clock`}
              {!myTurn && untilNext > 0 && (
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

      {boardLoading && <p className="mt-6 text-sm text-gray-500">Loading board…</p>}

      {board && config && (
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
          {/* LEFT: recommendations + available board */}
          <div className="flex flex-col gap-4">
            {/* recommendations */}
            <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
              <div className="mb-3 flex items-center gap-2">
                <h2 className="text-sm font-semibold text-white">
                  {myTurn ? "Recommended picks — your turn" : "Best available for you"}
                </h2>
                <Info className="h-3.5 w-3.5 text-gray-600" />
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
                          {r.player.team ?? "FA"} · {r.player.pos}{r.player.posRank}
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
                      onClick={() => draftPlayer(r.player.id)}
                      className="bg-[#10b981] font-semibold text-[#0a0a0a] hover:bg-[#059669]"
                    >
                      Draft
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
                    className="w-40 rounded-md border border-[#262626] bg-[#0a0a0a] py-1.5 pl-7 pr-2 text-xs text-white placeholder:text-gray-600"
                  />
                </div>
                <div className="flex gap-1">
                  {["ALL", ...POSITIONS].map((p) => (
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
              <div className="max-h-[520px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-[#0f0f0f] text-left text-[11px] uppercase tracking-wide text-gray-600">
                    <tr>
                      <th className="py-1.5 pl-1 font-medium">#</th>
                      <th className="py-1.5 font-medium">Player</th>
                      <th className="py-1.5 text-right font-medium">Pts</th>
                      <th className="py-1.5 text-right font-medium">VOR</th>
                      <th className="py-1.5 pr-1 text-right font-medium"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {available.slice(0, 250).map((p) => (
                      <tr key={p.id} className="border-t border-[#171717] hover:bg-[#141414]">
                        <td className="py-1.5 pl-1 text-xs text-gray-600">{p.ovrRank}</td>
                        <td className="py-1.5">
                          <div className="flex items-center gap-2">
                            <PosBadge pos={p.pos} small />
                            <span className="text-white">{p.name}</span>
                            <span className="text-xs text-gray-600">
                              {p.team ?? "FA"} · {p.pos}{p.posRank}
                            </span>
                            {p.rookie && <span className="rounded bg-sky-500/15 px-1 text-[10px] text-sky-300">R</span>}
                          </div>
                        </td>
                        <td className="py-1.5 text-right text-gray-300">{p.pts?.toFixed(0)}</td>
                        <td className="py-1.5 text-right text-gray-400">{p.vor?.toFixed(0)}</td>
                        <td className="py-1.5 pr-1 text-right">
                          <button
                            onClick={() => draftPlayer(p.id)}
                            className="rounded border border-[#2a2a2a] px-2 py-0.5 text-xs text-gray-400 hover:border-[#10b981] hover:text-[#10b981]"
                          >
                            Draft
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
                <span className="ml-auto text-xs text-gray-600">{s.player.vor?.toFixed(0)}</span>
              </>
            ) : (
              <span className="text-xs text-gray-700">empty</span>
            )}
          </div>
        ))}
      </div>
      {hasKdst && (
        <p className="mt-3 text-[11px] leading-snug text-gray-600">
          K &amp; DST aren&apos;t projected (offensive skill only) — draft them late; they won&apos;t appear on the board.
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
