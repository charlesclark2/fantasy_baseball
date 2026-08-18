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
import {
  GripVertical,
  Printer,
  Search,
  Star,
  Ban,
  Scissors,
  RotateCcw,
  Copy,
  StickyNote,
  Layers,
  ExternalLink,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Picker } from "@/components/ui/picker"
import { ALL_ROWS, InfoTip, PosBadge, num, teamLabel } from "@/components/fantasy/shared"
import { type LeagueConfigMeta, type Player } from "@/lib/draft-optimizer"
import {
  EMPTY_DOC,
  MAX_NOTE_LEN,
  applyDoc,
  baseOrder,
  boardKey,
  cheatSheet,
  customTiers,
  divergence,
  isEmptyDoc,
  moveTo,
  ourTierBreaks,
  reconcile,
  setNote,
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
  /** `warning` is set when the write LANDED but did not come back carrying everything we sent —
   *  see `onSave`. "Saved" and "saved except the part you just typed" are different facts. */
  | { kind: "saved"; at: string; warning?: string }
  | { kind: "error"; message: string }
  /** ⭐ DISTINCT FROM `idle`. "You have nothing saved" and "we could not read what you have saved"
   *  are different facts, and only one of them is ours to state. Collapsing them tells a user their
   *  work is gone on any transient read failure. */
  | { kind: "unreadable" }

export function BigBoard() {
  const { data: manifest, isLoading: manifestLoading, error: manifestError } = useFantasyManifest()
  const { data: savedLeagues } = useSavedLeagues()
  const { data: savedBoards, isLoading: savedLoading, isError: savedError } = useCustomBoards()
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
  /** Which row's note editor is open. One at a time — a board with two hundred textareas mounted is
   *  a real interaction cost, and the note is a thing you write about ONE player. */
  const [noteFor, setNoteFor] = useState<string | null>(null)
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
    // ⭐ A FAILED READ IS NOT AN EMPTY ACCOUNT (E9.46). Falling through here would load `EMPTY_DOC`
    // and the status line would say "nothing saved for this board yet" — a confident statement about
    // the user's own data that we are in no position to make, and the one most likely to make them
    // start again from scratch over a saved board that is sitting there intact. The board still
    // renders (it is ours, and it is useful); what changes is that we do not claim anything.
    if (savedError) {
      setSaveState({ kind: "unreadable" })
      return
    }
    loadedFor.current = key
    // ⚠️ EVERY FIELD READ WITH `??`. The API Lambda ships only via a manual `deploy.sh` (NF-C0), so
    // a board stored before a field existed — or returned by a backend that predates it — must read
    // as "empty", never as `undefined` propagating into the render.
    const next = stored
      ? {
          order: stored.order ?? [],
          tier_breaks: stored.tier_breaks ?? [],
          tags: stored.tags ?? {},
          notes: stored.notes ?? {},
        }
      : EMPTY_DOC
    // Anything referring to a player we no longer publish is dropped HERE and COUNTED — a board
    // saved in August can legitimately lose rows to a re-export, and shortening someone's ranking
    // without saying so reads as "the tool lost my work".
    const rec = reconcile(board, next)
    setDoc(rec.doc)
    setDropped(rec.droppedOrder + rec.droppedBreaks + rec.droppedTags + rec.droppedNotes)
    setSaveState({ kind: "idle" })
  }, [board, key, savedLoading, savedError, stored])

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
      const saved = await saveBoard.mutateAsync({ ...doc, config: configName, size })
      // ⭐ COMPARE WHAT CAME BACK WITH WHAT WE SENT. The API Lambda has NO CD (NF-C0): `frontend/`
      // auto-deploys on merge while the backend ships only via a manual `deploy.sh`, and the
      // request models do not set `extra="forbid"` — so a backend that predates the `notes` field
      // ACCEPTS the field, IGNORES it and returns 200. That is the E8.6 silent-save defect exactly:
      // the user types a note, sees "✓ Saved", reloads, and the note is gone with no error
      // anywhere. The response already carries the stored record, so one comparison turns a phantom
      // revert into a sentence. Keyed on "we sent notes and got none back" — not on a per-note
      // diff, which would also fire on a legitimate truncation.
      const sentNotes = Object.keys(doc.notes ?? {}).length
      const keptNotes = Object.keys(saved?.notes ?? {}).length
      setSaveState({
        kind: "saved",
        at: new Date().toLocaleTimeString(),
        warning:
          sentNotes > 0 && keptNotes === 0
            ? "Your order and tags were saved, but your notes were not — this account is talking to a version of our API that does not store them yet. Please try again later."
            : undefined,
      })
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

  /**
   * Seed the user's tier breaks from ours.
   *
   * ⚠️ IT TIERS THE DEPTH ON SCREEN, not the whole board — `assignTiers` sizes a tier as a fraction
   * of the pool it is given, so handing it all 858 rows returns groups of 40 (measured), which is
   * the whole of the first four rounds in one block and no more use on a cheat sheet than the
   * single tier it replaced. At the default depth of 200 it returns 14 groups of 8–27.
   */
  const seedOurTiers = () =>
    edit((d) => (board ? { ...d, tier_breaks: ourTierBreaks(board, shownDepth) } : d))

  const resetBoard = () => {
    edit(() => EMPTY_DOC)
    setSheetOpen(false)
  }

  const sheet = useMemo(
    () => (board ? cheatSheet(board, doc, shownDepth) : []),
    [board, doc, shownDepth],
  )

  /** Whether the user has drawn any tiers at all. ⚠️ READ FROM THE DOCUMENT, never from the number
   *  of sections: with no breaks `cheatSheet` correctly returns ONE section numbered 1, and a
   *  sheet that prints "TIER 1" over all two hundred names reads as a broken tiering rather than as
   *  "you have not drawn any" — reported on the live surface. */
  const hasTiers = doc.tier_breaks.length > 0

  const sheetText = useMemo(() => {
    const lines: string[] = [
      `${config?.label ?? configName} · ${size}-team · ${SEASON} — my big board`,
    ]
    for (const t of sheet) {
      lines.push("")
      if (hasTiers) lines.push(`TIER ${t.tier}`)
      for (const r of t.rows) {
        const tag = r.tag === "target" ? " [TARGET]" : r.tag === "avoid" ? " [AVOID]" : ""
        lines.push(
          `${String(r.rank).padStart(3)}. ${r.player.name} (${r.player.pos}, ${teamLabel(r.player)})${tag}`,
        )
        if (r.note) lines.push(`     ${r.note}`)
      }
    }
    return lines.join("\n")
  }, [sheet, config, configName, size, hasTiers])

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
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-gray-400 print:hidden">
            {`Start with our ${SEASON} board for your league, then make it your own. Drag players up or down, draw your own tier breaks, flag who you are chasing and who you are passing on, and write yourself a note on anyone. Our rank, our projection and the market's ADP stay next to every row, so you can always see where you have moved away from us.`}
          </p>
        </div>
      </div>

      {/* ── board selection ───────────────────────────────────────────────────────────────── */}
      <div className="mt-5 rounded-lg border border-[#262626] bg-[#0f0f0f] p-4 print:hidden">
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
      <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-[#262626] bg-[#0f0f0f] px-4 py-3 print:hidden">
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
          {saveState.kind === "unreadable" && (
            <span className="text-amber-400">
              We couldn&apos;t load your saved boards just now, so this is our order rather than
              yours. Nothing has been lost — reload before you make changes.
            </span>
          )}
          {saveState.kind === "dirty" && (
            <span className="text-amber-400">Unsaved changes.</span>
          )}
          {saveState.kind === "saving" && <span className="text-gray-400">Saving…</span>}
          {saveState.kind === "saved" && !saveState.warning && (
            <span className="text-[#10b981]">✓ Saved at {saveState.at}</span>
          )}
          {saveState.kind === "saved" && saveState.warning && (
            <span className="text-amber-400">⚠ {saveState.warning}</span>
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
          {/* ⭐ THE ANSWER TO "MY WHOLE SHEET SAYS TIER 1". A board with no breaks drawn is one
              flat list of two hundred names, which is not what anyone reads at a draft table. This
              seeds the breaks from OUR published tier structure (the same VOR-gap tiering the
              Rankings board and the optimizer use) so the user starts from a real grouping and
              edits it, rather than from nothing. It writes the breaks into their document — they
              are the user's from that moment, and every one of them can be moved or removed. */}
          <button
            onClick={seedOurTiers}
            data-testid="big-board-seed-tiers"
            className="rounded-md border border-[#262626] px-3 py-1.5 text-xs text-gray-300 hover:border-[#3a3a3a] hover:text-white"
          >
            <Layers className="mr-1 inline h-3.5 w-3.5" />
            Use our tiers
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
        <p data-testid="big-board-dropped" className="mt-2 text-xs text-amber-400 print:hidden">
          {dropped} {dropped === 1 ? "entry" : "entries"} from your saved board referred to players
          who are no longer on the {SEASON} board, and have been dropped. Save to keep the tidied
          version.
        </p>
      )}
      {maxBoards != null && (savedBoards?.boards.length ?? 0) >= maxBoards && !stored && (
        <p className="mt-2 text-xs text-amber-400 print:hidden">
          You are keeping {maxBoards} custom boards, which is the limit. Saving this one will be
          refused until you delete another.
        </p>
      )}

      {boardLoading && <p className="mt-6 text-sm text-gray-500">Loading board…</p>}

      {board && !sheetOpen && (
        <>
          {/* ── filters ──────────────────────────────────────────────────────────────────── */}
          <div className="mt-4 flex flex-wrap items-center gap-2 print:hidden">
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

          <IconLegend />

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
              <div className="min-w-[780px]">
                <div className="grid grid-cols-[32px_44px_1fr_52px_58px_52px_52px_58px_120px] items-center gap-2 border-b border-[#1f1f1f] px-3 py-2 text-[10px] uppercase tracking-wide text-gray-600">
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
                  <span className="text-right">Tier · tag · note</span>
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
                  const note = doc.notes?.[p.id] ?? ""
                  const editing = noteFor === p.id
                  return (
                    // ⚠️ THE WRAPPER CARRIES `data-row-index`, NOT THE GRID. A row can be two
                    // elements tall (its note sits under it), and the drag handler resolves a drop
                    // target with `elementFromPoint(...).closest("[data-row-index]")` — so if the
                    // index lived on the grid alone, dragging over an open note would resolve to
                    // nothing and the row under the cursor would silently not be the drop target.
                    <div
                      key={p.id}
                      data-testid="big-board-row"
                      data-row-index={index}
                      data-player-id={p.id}
                      data-tier={tier}
                      className={`${
                        isBreak ? "border-t-2 border-t-[#10b981]/40" : "border-t border-t-[#161616]"
                      } ${dragId === p.id ? "bg-[#10b981]/10" : ""} ${
                        tag === "avoid" ? "opacity-60" : ""
                      }`}
                    >
                      <div className="grid grid-cols-[32px_44px_1fr_52px_58px_52px_52px_58px_120px] items-center gap-2 px-3 py-1.5 text-sm">
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
                          // ⚠️ `text-base` ON MOBILE IS NOT COSMETIC. A raw control under 16px makes
                          // iOS auto-zoom on focus and mis-anchor any native picker on the page — the
                          // defect `components/ui/picker.tsx` exists because of. Pinned by
                          // `test_mobile_form_control_guard.py`, which is what caught this one.
                          className="w-full rounded border border-[#1f1f1f] bg-[#0a0a0a] px-1 py-0.5 text-center text-base text-white sm:text-xs"
                        />

                        <div className="flex min-w-0 items-center gap-2">
                          <PosBadge pos={p.pos} />
                          {/* ⭐ A NEW TAB, DELIBERATELY. This board holds unsaved work in component
                              state; navigating away in the same tab throws away every drag since
                              the last save, and a player card is something you glance at mid-edit.
                              `rel="noopener noreferrer"` because `target="_blank"` otherwise hands
                              the opened page a live `window.opener` handle back to this one. */}
                          <Link
                            href={`/fantasy/player/${encodeURIComponent(p.id)}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            title={`Open ${p.name} in a new tab`}
                            data-testid="big-board-player-name"
                            className="group flex min-w-0 items-center gap-1 truncate text-white hover:text-sky-300"
                          >
                            <span className="truncate">{p.name}</span>
                            <ExternalLink className="h-3 w-3 shrink-0 text-gray-700 group-hover:text-sky-300" />
                          </Link>
                          <span className="whitespace-nowrap text-xs text-gray-600">
                            {teamLabel(p)}
                            {p.bye != null ? ` · Bye ${p.bye}` : ""}
                          </span>
                          <span className="whitespace-nowrap rounded border border-[#262626] px-1 text-[10px] text-gray-500">
                            T{tier}
                          </span>
                        </div>

                        <span
                          data-testid="big-board-our-rank"
                          className="text-right text-xs text-gray-400"
                        >
                          {ourRank.get(p.id) ?? "—"}
                        </span>
                        <span className="text-right text-xs text-gray-300">{num(p.pts, 0)}</span>
                        <span className="text-right text-xs text-gray-400">{num(p.vor, 0)}</span>
                        <span className="text-right text-xs text-gray-500">{num(p.adp, 1)}</span>
                        <span
                          data-testid="big-board-delta"
                          className={`text-right text-xs ${
                            delta > 0
                              ? "text-sky-400"
                              : delta < 0
                                ? "text-amber-400"
                                : "text-gray-700"
                          }`}
                        >
                          {delta === 0 ? "—" : delta > 0 ? `+${delta}` : String(delta)}
                        </span>

                        <div className="flex items-center justify-end gap-1">
                          <IconToggle
                            on={isBreak}
                            onClick={() => edit((d) => toggleTierBreak(d, p.id))}
                            testId="big-board-tier-break"
                            label={`Start a new tier at ${p.name}`}
                            title="Start a new tier here"
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
                            title="Target — someone you are chasing"
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
                            title="Avoid — someone you are passing on"
                            onClass="border-rose-500/50 text-rose-400"
                          >
                            <Ban className="h-3.5 w-3.5" />
                          </IconToggle>
                          <IconToggle
                            on={!!note}
                            onClick={() => setNoteFor((cur) => (cur === p.id ? null : p.id))}
                            testId="big-board-note-toggle"
                            label={note ? `Edit your note on ${p.name}` : `Add a note on ${p.name}`}
                            title="Your own note on this player"
                            onClass="border-amber-500/50 text-amber-400"
                          >
                            <StickyNote className="h-3.5 w-3.5" />
                          </IconToggle>
                        </div>
                      </div>

                      {/* The note: an editor while it is open, otherwise the text itself. It is
                          rendered under the row rather than inside the grid because a note is a
                          sentence and the grid is a table of numbers — squeezing it into a cell
                          would either truncate it or make every row as tall as its longest note. */}
                      {editing && (
                        <div className="flex items-start gap-2 px-3 pb-2 pl-[76px]">
                          <textarea
                            autoFocus
                            value={note}
                            maxLength={MAX_NOTE_LEN}
                            onChange={(e) => edit((d) => setNote(d, p.id, e.target.value))}
                            onKeyDown={(e) => {
                              if (e.key === "Escape" || (e.key === "Enter" && !e.shiftKey)) {
                                e.preventDefault()
                                setNoteFor(null)
                              }
                            }}
                            placeholder={`Why ${p.name} sits here — for you, at the draft table.`}
                            aria-label={`Your note on ${p.name}`}
                            data-testid="big-board-note-input"
                            rows={2}
                            className="w-full max-w-2xl rounded border border-[#262626] bg-[#0a0a0a] px-2 py-1 text-base text-gray-200 placeholder:text-gray-700 sm:text-xs"
                          />
                          <button
                            onClick={() => setNoteFor(null)}
                            data-testid="big-board-note-done"
                            className="mt-0.5 shrink-0 rounded border border-[#262626] px-2 py-1 text-xs text-gray-400 hover:text-white"
                          >
                            Done
                          </button>
                          <span className="mt-1.5 shrink-0 text-[10px] text-gray-700">
                            {note.length}/{MAX_NOTE_LEN}
                          </span>
                        </div>
                      )}
                      {!editing && note && (
                        <p
                          data-testid="big-board-note-text"
                          className="px-3 pb-1.5 pl-[76px] text-xs italic text-amber-400/80"
                        >
                          {note}
                        </p>
                      )}
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
          hasTiers={hasTiers}
          onSeedTiers={seedOurTiers}
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

/**
 * What the four buttons on every row mean, in words.
 *
 * ⭐ THIS EXISTS BECAUSE THE ICONS ARE NOT SELF-EXPLANATORY, and one of them genuinely is not
 * guessable: a pair of scissors is a tier CUT, which nobody reads off the glyph, and it sat in a
 * column headed "Tag" while not being a tag at all. Reported on the live surface — a star and a no-
 * entry sign can be inferred and the scissors could not. A `title` alone would not have fixed it:
 * there is no hover on a phone, which is where a draft board is read.
 */
function IconLegend() {
  return (
    <div
      data-testid="big-board-legend"
      className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-gray-500 print:hidden"
    >
      <span className="text-gray-600">What the buttons on each row do:</span>
      <span className="inline-flex items-center gap-1">
        <Scissors className="h-3 w-3 text-[#10b981]" />
        start a new tier at this player
      </span>
      <span className="inline-flex items-center gap-1">
        <Star className="h-3 w-3 text-sky-400" />
        target — someone you are chasing
      </span>
      <span className="inline-flex items-center gap-1">
        <Ban className="h-3 w-3 text-rose-400" />
        avoid — someone you are passing on
      </span>
      <span className="inline-flex items-center gap-1">
        <StickyNote className="h-3 w-3 text-amber-400" />
        write yourself a note
      </span>
      <span className="inline-flex items-center gap-1">
        <GripVertical className="h-3 w-3 text-gray-600" />
        drag to move, or type a rank
      </span>
    </div>
  )
}

function IconToggle({
  on,
  onClick,
  testId,
  label,
  title,
  onClass,
  children,
}: {
  on: boolean
  onClick: () => void
  testId: string
  label: string
  /** The hover explanation. ⚠️ A `title` is a MOUSE affordance and nothing else — it is why the
   *  legend above the board exists rather than being the whole answer: on a phone there is no
   *  hover, and an icon whose only explanation is a tooltip is an unexplained icon there. */
  title?: string
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
      title={title ?? label}
      className={`rounded border px-1.5 py-1 ${
        on ? onClass : "border-[#1f1f1f] text-gray-700 hover:text-gray-400"
      }`}
    >
      {children}
    </button>
  )
}

/**
 * The draft-day sheet: the user's tiers, in their order, with their tags and their notes — and
 * deliberately WITHOUT our numbers.
 *
 * ⭐ THE NUMBERS ARE LEFT OFF ON PURPOSE. The editing view exists to show our read beside theirs;
 * this one is what gets printed and read at pick 4.11, where a column of projections beside a
 * ranking the user has already overridden is noise that invites second-guessing a decision they
 * made deliberately. The tier, the tag and their own note are the decisions; those are what print.
 *
 * ══ PRINTING ══════════════════════════════════════════════════════════════════════════════════
 *
 * ⚠️ `window.print()` PRINTS THE PAGE, NOT THIS COMPONENT. The first cut relied on the screen
 * layout being good enough on paper and it was not: the nav bar, the format pickers and the save
 * bar all printed, the dark-on-dark text came out as pale grey on white, and the sheet paginated
 * mid-tier. So the chrome is `print:hidden` at every one of its sources, the colour reset lives in
 * `globals.css` under `@media print` (one rule, rather than a `print:text-black` on every span
 * that would silently miss the next one added), and each tier block is `break-inside-avoid` so a
 * group stays on one page.
 *
 * ⭐ AND THE SHEET PRINTS ITS OWN HEADER. The browser's is a URL and a timestamp; ours is the
 * league, the format and the date the board was printed — the three things that tell you, weeks
 * later at a table with two sheets in front of you, which board this is.
 */
function CheatSheet({
  sections,
  title,
  shown,
  total,
  onCopy,
  copied,
  empty,
  hasTiers,
  onSeedTiers,
}: {
  sections: ReturnType<typeof cheatSheet>
  title: string
  shown: number
  total: number
  onCopy: () => void
  copied: boolean
  empty: boolean
  /** Whether the user has drawn ANY tier breaks. Not derivable from `sections.length` — one
   *  section is what both "no tiers" and "one enormous tier" look like. */
  hasTiers: boolean
  onSeedTiers: () => void
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

      {/* ⭐ "YOU HAVE NOT DRAWN ANY TIERS" IS A STATE, NOT AN ERROR — and it must not look like one.
          With no breaks every player is in tier 1, which printed as a single "TIER 1" heading over
          the whole sheet and read as a broken tiering. The heading is dropped, the fact is stated,
          and the one-click way out is right here rather than back on the board. */}
      {!hasTiers && (
        <p
          data-testid="big-board-no-tiers"
          className="mb-3 text-xs text-gray-500 print:hidden"
        >
          You haven&apos;t drawn any tiers, so this prints as one continuous list.{" "}
          <button
            onClick={onSeedTiers}
            data-testid="big-board-sheet-seed-tiers"
            className="text-sky-400 underline underline-offset-2 hover:text-sky-300"
          >
            Start from our tiers
          </button>{" "}
          and move them where you want, or draw your own with the scissors on any row.
        </p>
      )}

      <div className="print-sheet rounded-lg border border-[#262626] bg-[#0f0f0f] p-4 print:border-0 print:p-0">
        {/* Print-only. On screen the league and format are in the picker two inches above; on
            paper there is no picker, and a cheat sheet that does not say which league it is for is
            the one you pick up at the wrong draft. */}
        <div className="mb-3 hidden items-baseline justify-between border-b border-black pb-1 print:flex">
          <span className="text-sm font-semibold">{title} — my big board</span>
          <span className="text-[10px]">
            {shown} of {total} · printed {new Date().toLocaleDateString()} · credencesports.com
          </span>
        </div>

        <h2 className="text-sm font-semibold text-white print:hidden">{title} — my big board</h2>

        {/* Two columns on paper: a 200-row sheet is 5 pages in one column and 3 in two, and a
            draft sheet you have to turn over twice is one you stop reading. */}
        <div className="mt-3 grid min-w-0 grid-cols-1 gap-4 print:mt-0 print:block print:columns-2 print:gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {sections.map((s) => (
            <div
              key={s.tier}
              data-testid="big-board-sheet-tier"
              className="min-w-0 break-inside-avoid"
            >
              {hasTiers && (
                <div className="mb-1 border-b border-[#262626] pb-1 text-[11px] font-semibold uppercase tracking-wide text-[#10b981] print:border-black">
                  Tier {s.tier}
                </div>
              )}
              <ol className="space-y-0.5">
                {s.rows.map((r) => (
                  <li
                    key={r.player.id}
                    data-testid="big-board-sheet-row"
                    className="break-inside-avoid text-xs text-gray-300"
                  >
                    <span className="flex min-w-0 items-baseline gap-1.5">
                      <span className="w-6 shrink-0 text-right text-gray-600">{r.rank}</span>
                      <span className="truncate">{r.player.name}</span>
                      <span className="shrink-0 text-gray-600">
                        {r.player.pos} · {teamLabel(r.player)}
                      </span>
                      {r.tag === "target" && <span className="shrink-0 text-sky-400">★</span>}
                      {r.tag === "avoid" && <span className="shrink-0 text-rose-400">✕</span>}
                    </span>
                    {r.note && (
                      <span
                        data-testid="big-board-sheet-note"
                        className="ml-[30px] block text-[11px] italic text-amber-400/80"
                      >
                        {r.note}
                      </span>
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
    <p className="mx-auto mt-8 max-w-3xl text-center text-[11px] leading-relaxed text-gray-600 print:mt-4 print:text-black">
      The order you start from is our {SEASON} projection scored for your league, and everything you
      change from it is yours. We keep our rank, our projection and the market&apos;s ADP beside
      every row so the difference is visible — but a difference is not a verdict: we have no way to
      know which of us is right about any one player, and nothing here claims we do. This is
      analysis, not betting advice.
    </p>
  )
}
