"use client"

// NF-C4 — the CUSTOM BIG BOARD.
//
// Our published (config, size) board, made the user's own: drag to reorder, draw your own tier
// breaks, tag a player TARGET or AVOID, save it, and take it to draft day as a printed cheat sheet.
//
// ══ THE PRODUCT DECISION, WHICH IS ALSO THE HONESTY DECISION ═══════════════════════════════════
//
// Every row keeps OUR rank, OUR projection, OUR VOR and the market's ADP visible BESIDE the user's
// rank, and a "vs us" column states how far they have moved him. We are not hiding the
// disagreement or grading it: we do not know which of us is right about any single player, and
// nothing on this screen implies we do. What the surface is for is letting someone hold their own
// read and ours at the same time — which is the opposite of a tool that quietly replaces one with
// the other.
//
// ⭐ IT RANKS NOTHING ITSELF. The starting order is `baseOrder` → `sortAvailable`, the SAME function
// the snake and auction optimizers sort their boards with; every rule below is in `lib/big-board`
// and this file only renders it. A local sort here would be the E9.61 two-renderers defect at its
// most damaging: the optimizer would recommend one order and the sheet printed from it would show
// another, with no way to tell which was ours.
//
// ⚠️ SAVING IS EXPLICIT AND ITS STATE IS ALWAYS ON SCREEN (E8.6). A save surface with no feedback
// is the silent-save class — a field the server drops, or a refusal, presents as a phantom revert
// with no error anywhere. The status line renders the SERVER's own sentence on failure; it never
// invents one, and it never shows "Saved" for a write that did not land.

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import { GripVertical, Printer, Search, Star, Ban, Scissors, RotateCcw, Copy } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Picker } from "@/components/ui/picker"
import { ALL_ROWS, InfoTip, PosBadge, num, teamLabel } from "@/components/fantasy/shared"
import { type LeagueConfigMeta, type Player } from "@/lib/draft-optimizer"
import {
  EMPTY_DOC,
  applyDoc,
  baseOrder,
  boardKey,
  cheatSheet,
  customTiers,
  divergence,
  isEmptyDoc,
  moveTo,
  reconcile,
  setTag,
  toggleTierBreak,
  type BigBoardDoc,
  type BoardTag,
} from "@/lib/big-board"
import {
  FANTASY_SEASON,
  isCustomSelection,
  useCustomBoards,
  useFantasyManifest,
  useResolvedBoard,
  useSaveCustomBoard,
  useSavedLeagues,
} from "@/lib/fantasy-queries"

const SEASON = FANTASY_SEASON
const FILTER_POSITIONS = ["QB", "RB", "WR", "TE", "K", "DST"] as const
/** How deep the board renders. A big board is a draft-day sheet, not a database view — and 858
 *  simultaneously-draggable rows is a real interaction cost on a phone. The depth is the user's
 *  choice and it bounds only the RENDER: the saved document and the ordering are untouched.
 *
 *  ⚠️ THE "WHOLE BOARD" OPTION IS A SENTINEL, NOT A NUMBER. Writing today's row count (858) here
 *  would make the label a claim about the board rather than about the choice — and a wrong one the
 *  first time an export lands on 870 rows, with nothing in the product to contradict it. `ALL_ROWS`
 *  is the same sentinel the Projections pager already uses. */
const DEPTHS = [100, 200, 300, ALL_ROWS] as const
const DEFAULT_DEPTH = 200

type SaveState =
  | { kind: "idle" }
  | { kind: "dirty" }
  | { kind: "saving" }
  | { kind: "saved"; at: string }
  | { kind: "error"; message: string }

export function BigBoard() {
  const { data: manifest, isLoading: manifestLoading, error: manifestError } = useFantasyManifest()
  const { data: savedLeagues } = useSavedLeagues()
  const { data: savedBoards, isLoading: savedLoading } = useCustomBoards()
  const saveBoard = useSaveCustomBoard()

  const [configName, setConfigName] = useState<string>("")
  const [size, setSize] = useState<number>(12)
  const [doc, setDoc] = useState<BigBoardDoc>(EMPTY_DOC)
  const [saveState, setSaveState] = useState<SaveState>({ kind: "idle" })
  const [search, setSearch] = useState("")
  const [posFilter, setPosFilter] = useState<string>("ALL")
  const [depth, setDepth] = useState<number>(DEFAULT_DEPTH)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [dragId, setDragId] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [dropped, setDropped] = useState(0)

  useEffect(() => {
    if (manifest && !configName) {
      setConfigName(
        manifest.configs.find((c) => c.name === "half_ppr")?.name ?? manifest.configs[0]?.name ?? "",
      )
      setSize(manifest.sizes.includes(12) ? 12 : manifest.sizes[0])
    }
  }, [manifest, configName])

  // A saved league drafts exactly like a preset (NF-C0b) and carries its own team count.
  const selectedLeague = isCustomSelection(configName)
    ? savedLeagues?.find((l) => `custom:${l.league_id}` === configName)
    : undefined
  useEffect(() => {
    if (selectedLeague && size !== selectedLeague.n_teams) setSize(selectedLeague.n_teams)
  }, [selectedLeague, size])

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

  const { board, isLoading: boardLoading } = useResolvedBoard(configName || null, size || null)

  const key = configName ? boardKey(configName, size) : ""
  const stored = useMemo(
    () => (savedBoards?.boards ?? []).find((b) => b.board_key === key),
    [savedBoards, key],
  )

  // ── loading a saved board ─────────────────────────────────────────────────────────────────────
  // ⚠️ RUNS ON (board, key) AND NOTHING ELSE. Including `doc` would re-load the stored document
  // over the user's in-progress edits on every drag — a surface that silently undoes your work.
  const loadedFor = useRef<string>("")
  useEffect(() => {
    if (!board || !key || savedLoading) return
    if (loadedFor.current === key) return
    loadedFor.current = key
    const next = stored
      ? { order: stored.order ?? [], tier_breaks: stored.tier_breaks ?? [], tags: stored.tags ?? {} }
      : EMPTY_DOC
    // Anything referring to a player we no longer publish is dropped HERE and COUNTED — a board
    // saved in August can legitimately lose rows to a re-export, and shortening someone's ranking
    // without saying so reads as "the tool lost my work".
    const rec = reconcile(board, next)
    setDoc(rec.doc)
    setDropped(rec.droppedOrder + rec.droppedBreaks + rec.droppedTags)
    setSaveState({ kind: "idle" })
  }, [board, key, savedLoading, stored])

  const edit = useCallback((fn: (d: BigBoardDoc) => BigBoardDoc) => {
    setDoc((d) => {
      const next = fn(d)
      return next === d ? d : next
    })
    setSaveState((s) => (s.kind === "saving" ? s : { kind: "dirty" }))
  }, [])

  // ── the user's board ──────────────────────────────────────────────────────────────────────────
  const ordered = useMemo(() => (board ? applyDoc(board, doc) : []), [board, doc])
  const tiers = useMemo(() => customTiers(ordered, doc), [ordered, doc])
  const moved = useMemo(() => (board ? divergence(board, doc) : new Map()), [board, doc])
  const ourRank = useMemo(
    () => new Map((board ? baseOrder(board) : []).map((p, i) => [p.id, i + 1])),
    [board],
  )

  /** The rows on screen. A filter NARROWS what is shown; it never changes the ranking, so a row's
   *  number is always its place on the whole board — a "#3" that means "third of the WRs I have
   *  filtered to" would be a different number wearing the same label. */
  /** The sentinel resolved against THIS board's real length — never a hardcoded row count. */
  const shownDepth = depth === ALL_ROWS ? ordered.length : depth

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase()
    const rows = ordered
      .slice(0, shownDepth)
      .map((p, i) => ({ player: p, index: i }))
      .filter(
        (r) =>
          (posFilter === "ALL" || r.player.pos === posFilter) &&
          (!q || r.player.name.toLowerCase().includes(q)),
      )
    return rows
  }, [ordered, shownDepth, posFilter, search])

  // ── drag to reorder ───────────────────────────────────────────────────────────────────────────
  //
  // Pointer events on WINDOW rather than HTML5 drag-and-drop or pointer capture. Two reasons, both
  // practical: the rows re-order under the cursor mid-drag (React moves the DOM node), which is
  // exactly the case pointer CAPTURE is unreliable for; and pointer events work on touch, where a
  // draft board is genuinely used. `touch-action: none` on the handle is what stops a drag from
  // scrolling the page instead.
  const dragRef = useRef<string | null>(null)
  useEffect(() => {
    if (!dragId) return
    const onMove = (e: PointerEvent) => {
      const id = dragRef.current
      if (!id) return
      const el = (document.elementFromPoint(e.clientX, e.clientY) as Element | null)?.closest(
        "[data-row-index]",
      )
      if (!el) return
      const target = Number(el.getAttribute("data-row-index"))
      if (!Number.isFinite(target)) return
      edit((d) => (board ? moveTo(board, d, id, target) : d))
    }
    const end = () => {
      dragRef.current = null
      setDragId(null)
    }
    window.addEventListener("pointermove", onMove)
    window.addEventListener("pointerup", end)
    window.addEventListener("pointercancel", end)
    return () => {
      window.removeEventListener("pointermove", onMove)
      window.removeEventListener("pointerup", end)
      window.removeEventListener("pointercancel", end)
    }
  }, [dragId, board, edit])

  const startDrag = (id: string) => (e: React.PointerEvent) => {
    e.preventDefault()
    dragRef.current = id
    setDragId(id)
  }

  /** Type a rank. The reachable path for a 150-place move, and the keyboard-accessible one —
   *  dragging across a scrolling list is neither. */
  const setRank = (id: string, raw: string) => {
    const n = Number(raw)
    if (!Number.isFinite(n) || n < 1) return
    edit((d) => (board ? moveTo(board, d, id, Math.round(n) - 1) : d))
  }

  const onSave = async () => {
    if (!configName) return
    setSaveState({ kind: "saving" })
    try {
      await saveBoard.mutateAsync({ ...doc, config: configName, size })
      setSaveState({ kind: "saved", at: new Date().toLocaleTimeString() })
    } catch (e) {
      // ⭐ THE SERVER'S OWN SENTENCE, VERBATIM. `apiFetch` preserves FastAPI's `detail`, so a
      // refusal to save (413 — the item budget) arrives already written for a person and already
      // saying that nothing was changed. Replacing it with a generic message here is precisely how
      // a precise explanation becomes an unexplained failure (`lib/api.ts::errorMessage`).
      setSaveState({
        kind: "error",
        message: e instanceof Error && e.message ? e.message : "Could not save this board.",
      })
    }
  }

  const resetBoard = () => {
    edit(() => EMPTY_DOC)
    setSheetOpen(false)
  }

  const sheet = useMemo(
    () => (board ? cheatSheet(board, doc, shownDepth) : []),
    [board, doc, shownDepth],
  )

  const sheetText = useMemo(() => {
    const lines: string[] = [
      `${config?.label ?? configName} · ${size}-team · ${SEASON} — my big board`,
    ]
    for (const t of sheet) {
      lines.push("", `TIER ${t.tier}`)
      for (const r of t.rows) {
        const tag = r.tag === "target" ? " [TARGET]" : r.tag === "avoid" ? " [AVOID]" : ""
        lines.push(
          `${String(r.rank).padStart(3)}. ${r.player.name} (${r.player.pos}, ${teamLabel(r.player)})${tag}`,
        )
      }
    }
    return lines.join("\n")
  }, [sheet, config, configName, size])

  const copySheet = async () => {
    try {
      await navigator.clipboard.writeText(sheetText)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2500)
    } catch {
      // Clipboard permission is not guaranteed in every context. The sheet is on screen and
      // printable either way, so this is a convenience that must never present as a broken page.
      setCopied(false)
    }
  }

  const customCount = doc.order.length
  const maxBoards = savedBoards?.max_boards ?? null

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold text-white">My Big Board</h1>
          <p className="mt-1 max-w-2xl text-sm text-gray-400">
            Start from our {SEASON} board for your league, then make it yours — drag players where
            you want them, draw your own tier breaks, and flag who you are chasing and who you are
            passing on. Our rank, projection and the market&apos;s ADP stay beside every row, so you
            can always see where you have moved away from us.
          </p>
        </div>
      </div>

      {/* ── board selection ───────────────────────────────────────────────────────────────── */}
      <div className="mt-5 rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
        {manifestLoading && <p className="text-sm text-gray-500">Loading league presets…</p>}
        {manifestError && (
          <p className="text-sm text-rose-400">Could not load the {SEASON} draft boards.</p>
        )}
        {manifest && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-[2fr_1fr_1fr]">
            <Field label="League format">
              <Picker
                value={configName}
                onValueChange={setConfigName}
                ariaLabel="Scoring format"
                className="w-full rounded-md border border-[#262626] bg-[#0a0a0a] px-3 py-2 text-base text-white sm:text-sm"
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
            </Field>
            <Field label="League size">
              <Picker
                value={String(size)}
                onValueChange={(v) => setSize(Number(v))}
                disabled={!!selectedLeague}
                ariaLabel="League size"
                className="w-full rounded-md border border-[#262626] bg-[#0a0a0a] px-3 py-2 text-base text-white disabled:opacity-60 sm:text-sm"
                options={(selectedLeague ? [selectedLeague.n_teams] : manifest.sizes).map((s) => ({
                  value: String(s),
                  label: `${s} teams`,
                }))}
              />
            </Field>
            <Field label="Board depth">
              <Picker
                value={String(depth)}
                onValueChange={(v) => setDepth(Number(v))}
                ariaLabel="Board depth"
                className="w-full rounded-md border border-[#262626] bg-[#0a0a0a] px-3 py-2 text-base text-white sm:text-sm"
                options={DEPTHS.map((d) => ({
                  value: String(d),
                  label: d === ALL_ROWS ? "Whole board" : `Top ${d}`,
                }))}
              />
            </Field>
          </div>
        )}
        {config && <p className="mt-2 text-xs text-gray-500">{config.description}</p>}
      </div>

      {/* ── save bar ──────────────────────────────────────────────────────────────────────── */}
      <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-[#262626] bg-[#0f0f0f] px-4 py-3">
        <Button
          onClick={onSave}
          disabled={saveState.kind === "saving" || !configName || !board}
          data-testid="big-board-save"
          className="bg-[#10b981] font-semibold text-[#0a0a0a] hover:bg-[#059669]"
        >
          Save board
        </Button>
        {/* ⭐ THE STATUS LINE IS NOT DECORATION — it is the only thing that distinguishes a save
            that landed from one that was refused, and E8.6's silent-save defect is exactly a save
            that looks identical in both cases. Its four states are rendered as text a person can
            read, and the failure state carries the SERVER's explanation, not ours. */}
        <span data-testid="big-board-save-status" className="text-xs">
          {saveState.kind === "idle" && (
            <span className="text-gray-500">
              {stored ? "Saved board loaded." : "Nothing saved for this board yet."}
            </span>
          )}
          {saveState.kind === "dirty" && (
            <span className="text-amber-400">Unsaved changes.</span>
          )}
          {saveState.kind === "saving" && <span className="text-gray-400">Saving…</span>}
          {saveState.kind === "saved" && (
            <span className="text-[#10b981]">✓ Saved at {saveState.at}</span>
          )}
          {saveState.kind === "error" && (
            <span className="text-rose-400">{saveState.message}</span>
          )}
        </span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <button
            onClick={() => setSheetOpen((v) => !v)}
            data-testid="big-board-sheet-toggle"
            className="rounded-md border border-[#262626] px-3 py-1.5 text-xs text-gray-300 hover:border-[#3a3a3a] hover:text-white"
          >
            <Printer className="mr-1 inline h-3.5 w-3.5" />
            {sheetOpen ? "Back to editing" : "Cheat sheet"}
          </button>
          <button
            onClick={resetBoard}
            data-testid="big-board-reset"
            className="rounded-md border border-[#262626] px-3 py-1.5 text-xs text-gray-400 hover:border-[#3a3a3a] hover:text-white"
          >
            <RotateCcw className="mr-1 inline h-3.5 w-3.5" />
            Reset to ours
          </button>
        </div>
      </div>

      {dropped > 0 && (
        <p data-testid="big-board-dropped" className="mt-2 text-xs text-amber-400">
          {dropped} {dropped === 1 ? "entry" : "entries"} from your saved board referred to players
          who are no longer on the {SEASON} board, and have been dropped. Save to keep the tidied
          version.
        </p>
      )}
      {maxBoards != null && (savedBoards?.boards.length ?? 0) >= maxBoards && !stored && (
        <p className="mt-2 text-xs text-amber-400">
          You are keeping {maxBoards} custom boards, which is the limit. Saving this one will be
          refused until you delete another.
        </p>
      )}

      {boardLoading && <p className="mt-6 text-sm text-gray-500">Loading board…</p>}

      {board && !sheetOpen && (
        <>
          {/* ── filters ──────────────────────────────────────────────────────────────────── */}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-600" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Find a player"
                aria-label="Find a player"
                data-testid="big-board-search"
                className="rounded-md border border-[#262626] bg-[#0a0a0a] py-1.5 pl-7 pr-3 text-base text-white placeholder:text-gray-600 sm:text-sm"
              />
            </div>
            {(["ALL", ...FILTER_POSITIONS] as const).map((p) => (
              <button
                key={p}
                onClick={() => setPosFilter(p)}
                data-testid="big-board-pos-filter"
                data-pos={p}
                className={`rounded-md border px-2.5 py-1.5 text-xs ${
                  posFilter === p
                    ? "border-[#10b981]/50 bg-[#10b981]/10 text-[#10b981]"
                    : "border-[#262626] text-gray-400 hover:text-white"
                }`}
              >
                {p === "DST" ? "D/ST" : p}
              </button>
            ))}
            <span className="ml-auto text-xs text-gray-600">
              {customCount > 0
                ? `${customCount} of the top ${ordered.length} in your own order`
                : "Still exactly our order"}
            </span>
          </div>

          {/* ⚠️ THE WIDE BOARD SCROLLS INSIDE THIS CONTAINER, NEVER ON THE PAGE (NF-C2.1). The row
              grid below declares a 720px minimum, which is wider than a phone — so without
              `overflow-x-auto` here that width propagates to the document and the WHOLE PAGE gets a
              horizontal scrollbar, with the save bar and the honest note dragged off screen.
              Measured at 2129px on the mock-draft surface before its fix.

              ⚠️ `min-w-0` IS BELT-AND-BRACES HERE, AND SAYING SO IS THE POINT — measured: removing
              it changes nothing today, because this container's parent is an ordinary BLOCK and a
              block child with `overflow-x-auto` cannot grow it. It becomes load-bearing the moment
              anyone wraps this in a flex row or a grid track (a side panel — exactly what the draft
              and auction surfaces have), because a flex/grid item's automatic minimum is its
              MIN-CONTENT width and `truncate`'s `white-space: nowrap` makes that the whole string.
              It is kept for that reason, not because it is doing work now; the RENDERED assertion
              that can actually fail is the E2E's page-overflow check at phone width. */}
          <div className="mt-3">
            <div
              data-testid="big-board-scroller"
              className="min-w-0 overflow-x-auto rounded-lg border border-[#262626] bg-[#0f0f0f]"
            >
              <div className="min-w-[720px]">
                <div className="grid grid-cols-[36px_44px_1fr_56px_64px_56px_56px_64px_92px] items-center gap-2 border-b border-[#1f1f1f] px-3 py-2 text-[10px] uppercase tracking-wide text-gray-600">
                  <span />
                  <span>My #</span>
                  <span>Player</span>
                  <span className="text-right">Our #</span>
                  <span className="text-right">Proj</span>
                  <span className="text-right">VOR</span>
                  <span className="text-right">ADP</span>
                  <span className="text-right">
                    vs us
                    <InfoTip label={null}>
                      How far you have moved this player from where our board had him. Positive means
                      you rank him higher than we do. It is a description of the difference, not a
                      score of it — we have no way to know which of us is right about any one player.
                    </InfoTip>
                  </span>
                  <span className="text-right">Tag</span>
                </div>

                {visible.length === 0 && (
                  <p className="px-3 py-6 text-sm text-gray-500">
                    No players match that filter.
                  </p>
                )}

                {visible.map(({ player: p, index }) => {
                  const tier = tiers.get(p.id) ?? 1
                  const isBreak = doc.tier_breaks.includes(p.id)
                  const delta = moved.get(p.id) ?? 0
                  const tag = doc.tags[p.id] ?? null
                  return (
                    <div
                      key={p.id}
                      data-testid="big-board-row"
                      data-row-index={index}
                      data-player-id={p.id}
                      data-tier={tier}
                      className={`grid grid-cols-[36px_44px_1fr_56px_64px_56px_56px_64px_92px] items-center gap-2 px-3 py-1.5 text-sm ${
                        isBreak ? "border-t-2 border-t-[#10b981]/40" : "border-t border-t-[#161616]"
                      } ${dragId === p.id ? "bg-[#10b981]/10" : ""} ${
                        tag === "avoid" ? "opacity-60" : ""
                      }`}
                    >
                      <button
                        onPointerDown={startDrag(p.id)}
                        data-testid="big-board-drag-handle"
                        aria-label={`Drag ${p.name}`}
                        className="cursor-grab touch-none text-gray-600 hover:text-gray-300"
                      >
                        <GripVertical className="h-4 w-4" />
                      </button>

                      <input
                        type="number"
                        min={1}
                        value={index + 1}
                        onChange={(e) => setRank(p.id, e.target.value)}
                        aria-label={`Rank for ${p.name}`}
                        data-testid="big-board-rank-input"
                        className="w-full rounded border border-[#1f1f1f] bg-[#0a0a0a] px-1 py-0.5 text-center text-xs text-white"
                      />

                      <div className="flex min-w-0 items-center gap-2">
                        <PosBadge pos={p.pos} />
                        <Link
                          href={`/fantasy/player/${encodeURIComponent(p.id)}`}
                          data-testid="big-board-player-name"
                          className="truncate text-white hover:text-sky-300"
                        >
                          {p.name}
                        </Link>
                        <span className="whitespace-nowrap text-xs text-gray-600">
                          {teamLabel(p)}
                          {p.bye != null ? ` · Bye ${p.bye}` : ""}
                        </span>
                        <span className="whitespace-nowrap rounded border border-[#262626] px-1 text-[10px] text-gray-500">
                          T{tier}
                        </span>
                      </div>

                      <span data-testid="big-board-our-rank" className="text-right text-xs text-gray-400">
                        {ourRank.get(p.id) ?? "—"}
                      </span>
                      <span className="text-right text-xs text-gray-300">{num(p.pts, 0)}</span>
                      <span className="text-right text-xs text-gray-400">{num(p.vor, 0)}</span>
                      <span className="text-right text-xs text-gray-500">{num(p.adp, 1)}</span>
                      <span
                        data-testid="big-board-delta"
                        className={`text-right text-xs ${
                          delta > 0 ? "text-sky-400" : delta < 0 ? "text-amber-400" : "text-gray-700"
                        }`}
                      >
                        {delta === 0 ? "—" : delta > 0 ? `+${delta}` : String(delta)}
                      </span>

                      <div className="flex items-center justify-end gap-1">
                        <IconToggle
                          on={isBreak}
                          onClick={() => edit((d) => toggleTierBreak(d, p.id))}
                          testId="big-board-tier-break"
                          label={`Tier break above ${p.name}`}
                          onClass="border-[#10b981]/50 text-[#10b981]"
                        >
                          <Scissors className="h-3.5 w-3.5" />
                        </IconToggle>
                        <IconToggle
                          on={tag === "target"}
                          onClick={() =>
                            edit((d) => setTag(d, p.id, tag === "target" ? null : "target"))
                          }
                          testId="big-board-target"
                          label={`Target ${p.name}`}
                          onClass="border-sky-500/50 text-sky-400"
                        >
                          <Star className="h-3.5 w-3.5" />
                        </IconToggle>
                        <IconToggle
                          on={tag === "avoid"}
                          onClick={() =>
                            edit((d) => setTag(d, p.id, tag === "avoid" ? null : "avoid"))
                          }
                          testId="big-board-avoid"
                          label={`Avoid ${p.name}`}
                          onClass="border-rose-500/50 text-rose-400"
                        >
                          <Ban className="h-3.5 w-3.5" />
                        </IconToggle>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>

          {ordered.length > shownDepth && (
            <p className="mt-2 text-xs text-gray-600">
              Showing the top {shownDepth} of {ordered.length}. Your saved board keeps every change
              you make, whatever depth you are viewing.
            </p>
          )}
        </>
      )}

      {board && sheetOpen && (
        <CheatSheet
          sections={sheet}
          title={`${config?.label ?? configName} · ${size}-team · ${SEASON}`}
          shown={Math.min(shownDepth, ordered.length)}
          total={ordered.length}
          onCopy={copySheet}
          copied={copied}
          empty={isEmptyDoc(doc)}
        />
      )}

      <HonestNote />
    </div>
  )
}

// ── sub-components ──────────────────────────────────────────────────────────────────────────────

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

function IconToggle({
  on,
  onClick,
  testId,
  label,
  onClass,
  children,
}: {
  on: boolean
  onClick: () => void
  testId: string
  label: string
  onClass: string
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      data-testid={testId}
      data-on={on ? "true" : "false"}
      aria-pressed={on}
      aria-label={label}
      className={`rounded border px-1.5 py-1 ${
        on ? onClass : "border-[#1f1f1f] text-gray-700 hover:text-gray-400"
      }`}
    >
      {children}
    </button>
  )
}

/**
 * The draft-day sheet: the user's tiers, in their order, with their tags — and deliberately WITHOUT
 * our numbers.
 *
 * ⭐ THE NUMBERS ARE LEFT OFF ON PURPOSE. The editing view exists to show our read beside theirs;
 * this one is what gets printed and read at pick 4.11, where a column of projections beside a
 * ranking the user has already overridden is noise that invites second-guessing a decision they
 * made deliberately. The tag and the tier are the decisions; those are what print.
 */
function CheatSheet({
  sections,
  title,
  shown,
  total,
  onCopy,
  copied,
  empty,
}: {
  sections: ReturnType<typeof cheatSheet>
  title: string
  shown: number
  total: number
  onCopy: () => void
  copied: boolean
  empty: boolean
}) {
  return (
    <div className="mt-4" data-testid="big-board-cheat-sheet">
      <div className="mb-3 flex flex-wrap items-center gap-2 print:hidden">
        <Button
          onClick={() => window.print()}
          data-testid="big-board-print"
          className="bg-[#1f1f1f] text-white hover:bg-[#2a2a2a]"
        >
          <Printer className="mr-1 h-4 w-4" /> Print
        </Button>
        <button
          onClick={onCopy}
          data-testid="big-board-copy"
          className="rounded-md border border-[#262626] px-3 py-1.5 text-xs text-gray-300 hover:text-white"
        >
          <Copy className="mr-1 inline h-3.5 w-3.5" />
          {copied ? "Copied" : "Copy as text"}
        </button>
        <span className="text-xs text-gray-600">
          {shown} of {total} players
          {empty ? " — this is still exactly our order; nothing has been customised yet." : ""}
        </span>
      </div>

      <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-4 print:border-0 print:bg-white print:text-black">
        <h2 className="text-sm font-semibold text-white print:text-black">{title} — my big board</h2>
        <div className="mt-3 grid min-w-0 grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {sections.map((s) => (
            <div key={s.tier} data-testid="big-board-sheet-tier" className="min-w-0">
              <div className="mb-1 border-b border-[#262626] pb-1 text-[11px] font-semibold uppercase tracking-wide text-[#10b981] print:text-black">
                Tier {s.tier}
              </div>
              <ol className="space-y-0.5">
                {s.rows.map((r) => (
                  <li
                    key={r.player.id}
                    data-testid="big-board-sheet-row"
                    className="flex min-w-0 items-baseline gap-1.5 text-xs text-gray-300 print:text-black"
                  >
                    <span className="w-6 shrink-0 text-right text-gray-600 print:text-black">
                      {r.rank}
                    </span>
                    <span className="truncate">{r.player.name}</span>
                    <span className="shrink-0 text-gray-600 print:text-black">
                      {r.player.pos} · {teamLabel(r.player)}
                    </span>
                    {r.tag === "target" && (
                      <span className="shrink-0 text-sky-400 print:text-black">★</span>
                    )}
                    {r.tag === "avoid" && (
                      <span className="shrink-0 text-rose-400 print:text-black">✕</span>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function HonestNote() {
  return (
    <p className="mx-auto mt-8 max-w-3xl text-center text-[11px] leading-relaxed text-gray-600">
      The order you start from is our {SEASON} projection scored for your league, and everything you
      change from it is yours. We keep our rank, our projection and the market&apos;s ADP beside
      every row so the difference is visible — but a difference is not a verdict: we have no way to
      know which of us is right about any one player, and nothing here claims we do. This is
      analysis, not betting advice.
    </p>
  )
}
