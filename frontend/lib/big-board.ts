// big-board.ts — NF-C4: the user's OWN ranking of our board, and nothing else.
//
// ══ WHAT THIS MODULE IS ═══════════════════════════════════════════════════════════════════════
//
// The Custom Big Board lets a user reorder, tier and tag OUR published (config, size) board and
// take the result to draft day. This file is the whole rule set: pure, synchronous, no React, no
// fetch — so the component renders it and the tests drive it through exactly the same code.
//
// ⭐ IT DOES NOT RANK ANYTHING. The base ordering is `sortAvailable` from `lib/draft-optimizer`,
// the SAME function the snake optimizer and the auction tool sort their boards with. A second
// ranker here would be the E9.61 "two renderers of one field are two rule sets" defect in its most
// consequential form: the draft optimizer would recommend one order and the cheat sheet the user
// printed from it would show another, and neither screen would say which was ours. Everything
// below is a PERMUTATION of that order plus two annotations.
//
// ══ THE STORED SHAPE, AND WHY IT IS A PREFIX ══════════════════════════════════════════════════
//
// A saved board is `{order, tier_breaks, tags}`, and `order` is an explicit PREFIX — the first N
// player ids in the user's order — with everything after it following OUR order. Three reasons,
// and the third is the one that made the choice:
//
//   1. It is exact. `applyDoc` reconstructs the user's view byte-for-byte (proved below), so a
//      printed cheat sheet and the screen it came from cannot disagree.
//   2. It is small — bounded by HOW DEEP THE USER WORKS, never by the board's length. A move only
//      disturbs the rows between its two ends, so the prefix runs to `max(from, to) + 1`: curating
//      a top-50 board stores ~50 ids (~0.7 KB) whether the board is 858 rows or 3,000. ⚠️ IT IS NOT
//      "the number of players you moved" — measured, promoting #301 to #12 stores 301 ids (~4.2 KB),
//      because every row in between shifts down one. That still beats a full copy (858 ids, ~12 KB)
//      and, crucially, does not grow when the board does. This matters because all of a user's
//      state — every league, every roster, their portfolio, their platform tokens — lives in ONE
//      400 KB DynamoDB item (NF-C6P3), and an overflow there is not a degraded feature, it is a
//      user row that can never be written again.
//   3. ⭐ It REINHERITS our re-exports. The tail is recomputed from whatever board is published
//      today, so a player we move, add or re-rank after the user saved arrives automatically. A
//      stored full copy would silently freeze the user's board at the vintage they first opened it
//      — which on a draft-season board that re-exports weekly is a wrong answer that looks exactly
//      like a right one.
//      ⚠️ THE CONSEQUENCE, STATED BECAUSE IT IS EASY TO EXPECT THE OTHER THING: a player published
//      AFTER the user curated a region enters at the top of the UN-CURATED tail, not at our rank
//      inside the curated part. Curate the top 200 and a September rookie arrives at 201, not at 4.
//      That is correct rather than a limitation — inserting him inside the prefix would silently
//      re-rank him above two hundred players the user placed deliberately — but it means a deep
//      curator has to look below their own region for new names. Pinned by the E2E spec.
//
// ⚠️ WHAT IT DELIBERATELY DOES NOT STORE: any of our numbers. Not one projection, VOR or ADP is
// persisted. The board is re-joined to the live one on every load, so a saved board can never
// serve a stale points figure, and the stored document is worthless to anyone who does not already
// have the (paid) board it references.

import { positionTierMap, sortAvailable, type Player } from "@/lib/draft-optimizer"

/** A row's user tag. Two states plus "untagged". A tag is the DECISION ("I want him" / "I am
 *  passing"); the reason lives in `notes`, which is a separate field with a very different size
 *  profile against the shared item budget — see `MAX_NOTE_LEN`. */
export type BoardTag = "target" | "avoid"

/**
 * The longest note we let a row carry, and the ONLY reason there is a limit: every note is bytes in
 * the one 400 KB DynamoDB item that holds all of a user's state (NF-C6P3).
 *
 * ⚠️ THE SERVER OWNS THE REAL CAP (`MAX_BIG_BOARD_NOTE_LEN` in `app/backend/models/fantasy.py`) and
 * truncates on save. This constant exists so the textarea stops the user at the same place instead
 * of letting them type a paragraph that is silently shortened after the fact — the one-thing-two-
 * owners class (INC-30/36/38) in its mild form. The two numbers are pinned equal by
 * `test_nf_c4_custom_big_board.py`; change one and that guard goes red.
 */
export const MAX_NOTE_LEN = 200

/**
 * One saved board, exactly as it travels on the wire and exactly as it is stored.
 *
 * ⭐ SNAKE_CASE ON PURPOSE, matching `SavedLeague`. One name per field across TS, the API model and
 * DynamoDB means there is no mapping layer, and a mapping layer is where a field gets silently
 * dropped (E9.41).
 */
export interface BigBoardDoc {
  /** Player ids, in the user's order. An explicit PREFIX — see the module header. */
  order: string[]
  /** Ids that START a new tier. A break before the first row is meaningless and is ignored. */
  tier_breaks: string[]
  /** `{player id -> tag}`. Absent id ⇒ untagged. */
  tags: Record<string, BoardTag>
  /** `{player id -> the user's own note}`. Absent id ⇒ no note. Empty strings are never stored —
   *  a cleared note removes the key, so an untouched row costs nothing against the item budget. */
  notes: Record<string, string>
}

/**
 * A stored board as the API returns it: the document plus which board it belongs to.
 *
 * ⚠️ EVERY DOCUMENT FIELD IS OPTIONAL HERE, ON PURPOSE. This is a WIRE type, and the API Lambda
 * ships only via a manual `deploy.sh` while `frontend/` auto-deploys on merge (NF-C0) — so a
 * running backend can predate a field this client knows about, and a board stored before a field
 * existed reads back without it. `Partial` makes the compiler insist every read is defaulted
 * (`stored.notes ?? {}`) instead of letting `undefined` propagate into a render as a crash.
 */
export interface SavedBigBoard extends Partial<BigBoardDoc> {
  board_key: string
  config: string
  size: number
  updated_at?: string | null
  created_at?: string | null
}

export const EMPTY_DOC: BigBoardDoc = { order: [], tier_breaks: [], tags: {}, notes: {} }

/** Whether a document carries any user intent at all. Used to decide "Saved" vs "nothing to save"
 *  — an empty board is not a state worth spending a write (or a byte of the item budget) on. */
export function isEmptyDoc(doc: BigBoardDoc): boolean {
  return (
    doc.order.length === 0 &&
    doc.tier_breaks.length === 0 &&
    Object.keys(doc.tags).length === 0 &&
    Object.keys(doc.notes ?? {}).length === 0
  )
}

/**
 * The board key a (config, size) pair saves under.
 *
 * ⚠️ The SERVER derives its own key from the same two fields and stores under that; this is the
 * client's local cache key only. They are computed the same way so a reader can match them by eye,
 * but nothing here is trusted by the writer — see `routers/fantasy.py::_big_board_key`.
 */
export function boardKey(config: string, size: number): string {
  return `${config}|${size}`
}

/**
 * OUR order for this board — the one the user is starting from and diverging from.
 *
 * ⭐ THE SHARED FUNCTION, NOT A LOCAL SORT. `sortAvailable` also holds K/DST below every real
 * candidate, which matters more here than anywhere else: this is the list a user prints and reads
 * at pick 4.11, and a D/ST interleaved at #56 on raw VOR (the live 2026-08-13 report that produced
 * `sortAvailable` in the first place) would be advice we had already decided not to give.
 */
export function baseOrder(board: Player[]): Player[] {
  return sortAvailable(board, { sortCol: "ovrRank", sortDir: "asc", deferLowPred: true })
}

/**
 * The user's board: their explicit prefix, then everything else in OUR order.
 *
 * Ids in `order` that are not on today's board are skipped (a player we no longer publish), and
 * players on today's board that the user never touched appear at their own place in the tail. Both
 * are silent HERE and reported by `reconcile` — this function has to stay total, because it runs
 * on every keystroke.
 */
export function applyDoc(board: Player[], doc: BigBoardDoc): Player[] {
  const base = baseOrder(board)
  if (doc.order.length === 0) return base
  const byId = new Map(base.map((p) => [p.id, p]))
  const prefix: Player[] = []
  const placed = new Set<string>()
  for (const id of doc.order) {
    const p = byId.get(id)
    // `placed` guards a duplicate id in a stored document. Without it one player would render
    // twice, collide on his React key, and be undraftable from one of the two rows.
    if (p && !placed.has(id)) {
      prefix.push(p)
      placed.add(id)
    }
  }
  return [...prefix, ...base.filter((p) => !placed.has(p.id))]
}

/**
 * Move one player to `toIndex` in the user's current view, returning the new document.
 *
 * ⭐ THE PREFIX IS TRIMMED TO THE DEEPEST CHANGED ROW, and that is what keeps a saved board small.
 * Everything below the last row that differs from OUR order is, by construction, our order with
 * the prefix removed — which is exactly what `applyDoc` rebuilds. So storing it would be storing a
 * copy of our own board.
 *
 * The identity that makes this exact: `next` is a permutation of `base`, and `next[i] === base[i]`
 * for every `i >= cut`. Therefore the set of ids in `next[0..cut)` equals the set in
 * `base[0..cut)`, so `base` minus the prefix is `base[cut..] === next[cut..]`. Pinned by
 * `test_nf_c4_custom_big_board.py` over a grid of moves rather than a few hand-picked ones.
 */
export function moveTo(board: Player[], doc: BigBoardDoc, id: string, toIndex: number): BigBoardDoc {
  const current = applyDoc(board, doc)
  const from = current.findIndex((p) => p.id === id)
  if (from < 0) return doc
  const to = Math.max(0, Math.min(current.length - 1, Math.trunc(toIndex)))
  if (to === from) return doc

  const ids = current.map((p) => p.id)
  ids.splice(to, 0, ids.splice(from, 1)[0])

  const baseIds = baseOrder(board).map((p) => p.id)
  let cut = 0
  for (let i = 0; i < ids.length; i++) if (ids[i] !== baseIds[i]) cut = i + 1
  return { ...doc, order: ids.slice(0, cut) }
}

/** Toggle a tier break at `id` (the row that STARTS the new tier). */
export function toggleTierBreak(doc: BigBoardDoc, id: string): BigBoardDoc {
  const has = doc.tier_breaks.includes(id)
  return {
    ...doc,
    tier_breaks: has ? doc.tier_breaks.filter((x) => x !== id) : [...doc.tier_breaks, id],
  }
}

/** Set or clear a row's tag. `null` removes the key entirely rather than storing a null — an
 *  untagged player must cost nothing against the item budget. */
export function setTag(doc: BigBoardDoc, id: string, tag: BoardTag | null): BigBoardDoc {
  const tags = { ...doc.tags }
  if (tag === null) delete tags[id]
  else tags[id] = tag
  return { ...doc, tags }
}

/**
 * Set or clear a row's note. Whitespace-only is a CLEAR, and a cleared note deletes the key rather
 * than storing `""` — an empty string is bytes in the shared item that mean nothing.
 *
 * ⛔⛔ DO NOT `.trim()` HERE. THIS RUNS ON EVERY KEYSTROKE. The first cut did, and the effect was
 * that the space a user typed was removed before it could ever be followed by another character —
 * so a note came out as "jmarrchaseisherebecauseiwantawrhigher". Reported on the live surface, and
 * it is one of those bugs that is obvious the moment you type into the box and invisible everywhere
 * else. ⚠️ IN PARTICULAR IT WAS INVISIBLE TO THE E2E, because Playwright's `fill()` sets the whole
 * value in ONE event — a per-keystroke defect needs `pressSequentially` to reach it, which is now
 * what the spec uses.
 *
 * Truncation stays (the box must not hold what the server will not store), and the whitespace-only
 * CLEAR reads `.trim()` without applying it. Normalisation happens once, on `trimNotes`, when the
 * editor closes and again before the save.
 */
export function setNote(doc: BigBoardDoc, id: string, text: string): BigBoardDoc {
  const notes = { ...(doc.notes ?? {}) }
  const raw = String(text ?? "").slice(0, MAX_NOTE_LEN)
  if (!raw.trim()) delete notes[id]
  else notes[id] = raw
  return { ...doc, notes }
}

/**
 * Normalise every note: trimmed, and gone if there is nothing left.
 *
 * ⭐ CALLED WHERE TYPING HAS STOPPED — when the editor closes, and again on the way to the server —
 * never per keystroke (see `setNote`). It is what keeps the local document byte-identical to what
 * the server stores, so a reload cannot appear to change a note the user never touched.
 */
export function trimNotes(doc: BigBoardDoc): BigBoardDoc {
  const notes: Record<string, string> = {}
  for (const [id, text] of Object.entries(doc.notes ?? {})) {
    const clean = text.trim()
    if (clean) notes[id] = clean
  }
  return { ...doc, notes }
}

/**
 * OUR tier breaks for the top `depth` rows of this board — the ids that start a new group.
 *
 * ⭐ WHAT THIS IS FOR. A user who has drawn no tiers has a sheet that is one flat list of two
 * hundred names, which is not what anyone reads at pick 4.11. This seeds their breaks from the
 * shared gap-tiering (`positionTierMap` → `assignTiers`, the same function that tiers a position on
 * the player page and drives the optimizer's tier-cliff line) applied to this board's own VOR
 * ordering, so the starting point is a real measured grouping rather than an invention of this
 * surface — and from there every break is theirs to move or delete.
 *
 * ⚠️ IT TIERS THE POOL, NOT THE WHOLE BOARD, AND THAT IS THE LOAD-BEARING ARGUMENT. `assignTiers`
 * bounds a tier's size as a FRACTION of the pool it is given (4%–15%, its own docstring: "both
 * bounds SCALE WITH THE POOL SIZE" to target ~7–25 tiers whatever `n` is). Handed all ~600
 * draftable rows it therefore returns tiers of 24–90 players — measured: 6 tiers covering the top
 * 200, ~35 players each, which is the whole of the first four rounds in one block and no more use
 * on a cheat sheet than the single tier it replaced. Handed the depth the user is actually working
 * at it returns groups you can read. So `depth` is a real parameter and not a convenience: seeding
 * at 100 and at 300 legitimately gives different structures, because a tier is relative to the pool
 * it is drawn from.
 *
 * ⚠️ TIERS ARE ASSIGNED ON VOR, THE BOARD IS ORDERED ON `ovrRank`, and the two need not agree
 * row-for-row. So a break is emitted only where the tier number goes UP relative to the deepest
 * tier seen so far: without that, a row whose VOR tier sits above its neighbour's would emit a
 * break, then the next row another one, and the "tiers" would oscillate into groups of one.
 *
 * ⚠️ K/DST ARE EXCLUDED VIA THE EXPORTER'S OWN `lowPred` FLAG, not a hardcoded position list. The
 * NF1.6 lesson is exactly this: K/DST stopped being null-VOR placeholders and a position list left
 * behind in the code kept claiming otherwise.
 */
export function ourTierBreaks(board: Player[], depth: number): string[] {
  const base = baseOrder(board)
  const pool = base.slice(0, Math.max(1, Math.trunc(depth)))
  const tiers = positionTierMap(
    pool.filter((p) => p.lowPred !== true),
    (p) => p.vor ?? 0,
  )
  const breaks: string[] = []
  let deepest = 0
  pool.forEach((p, i) => {
    const t = tiers.get(p.id)
    if (t == null) return
    if (i > 0 && t > deepest) breaks.push(p.id)
    deepest = Math.max(deepest, t)
  })
  return breaks
}

/**
 * `{player id -> the user's tier number}`, 1-based, in the order `rows` is already in.
 *
 * ⚠️ NOT `positionTierMap`. That one derives tiers from GAPS in our own numbers; this one is the
 * user's declaration, and the two must not be conflated — the whole point of the surface is that
 * the user is allowed to disagree with us. Both are rendered, side by side, labelled.
 */
export function customTiers(rows: Player[], doc: BigBoardDoc): Map<string, number> {
  const breaks = new Set(doc.tier_breaks)
  const out = new Map<string, number>()
  let tier = 1
  rows.forEach((p, i) => {
    if (i > 0 && breaks.has(p.id)) tier++
    out.set(p.id, tier)
  })
  return out
}

/**
 * Drop anything in `doc` that no longer exists on the board, and report how much.
 *
 * ⭐ REPORTED, NEVER SILENT. A board saved in August and opened in September can legitimately have
 * lost players (a retirement, a re-export that drops an unprojected row). Quietly shortening the
 * user's ranking would present as "the tool lost my work"; naming it is the difference between a
 * data change and a bug. `applyDoc` already ignores these, so this is about telling the user, not
 * about correctness of the render.
 */
export function reconcile(
  board: Player[],
  doc: BigBoardDoc,
): {
  doc: BigBoardDoc
  droppedOrder: number
  droppedTags: number
  droppedBreaks: number
  droppedNotes: number
} {
  const live = new Set(board.map((p) => p.id))
  const order = doc.order.filter((id) => live.has(id))
  const tier_breaks = doc.tier_breaks.filter((id) => live.has(id))
  const tags: Record<string, BoardTag> = {}
  for (const [id, t] of Object.entries(doc.tags)) if (live.has(id)) tags[id] = t
  const notes: Record<string, string> = {}
  for (const [id, n] of Object.entries(doc.notes ?? {})) if (live.has(id)) notes[id] = n
  return {
    doc: { order, tier_breaks, tags, notes },
    droppedOrder: doc.order.length - order.length,
    droppedTags: Object.keys(doc.tags).length - Object.keys(tags).length,
    droppedNotes: Object.keys(doc.notes ?? {}).length - Object.keys(notes).length,
    droppedBreaks: doc.tier_breaks.length - tier_breaks.length,
  }
}

/**
 * How far the user has moved a player from where WE had him: OUR index minus THEIRS.
 *
 * Positive ⇒ the user ranks him HIGHER than we do (he has climbed). Null when the row is not on
 * one of the two orders, which cannot happen for a live board but keeps the function total.
 *
 * ⭐ THE HONEST-ANALYTICS COLUMN. The product decision on this surface is that the user overrides
 * us and we say so plainly rather than hiding the disagreement — so the delta is rendered from OUR
 * order, on every row they moved, with no claim attached to either direction. We do not know which
 * of us is right and nothing here implies we do.
 */
export function divergence(board: Player[], doc: BigBoardDoc): Map<string, number> {
  const ours = new Map(baseOrder(board).map((p, i) => [p.id, i]))
  const out = new Map<string, number>()
  applyDoc(board, doc).forEach((p, i) => {
    const o = ours.get(p.id)
    if (o != null) out.set(p.id, o - i)
  })
  return out
}

/** One printed section of the draft-day cheat sheet: a user tier and the players in it. */
export interface CheatSheetTier {
  tier: number
  rows: { rank: number; player: Player; tag: BoardTag | null; moved: number; note: string | null }[]
}

/**
 * The cheat sheet, grouped by the user's OWN tiers.
 *
 * `limit` is the printed depth. It bounds the PRINT, never the stored document — truncating what a
 * user saved would be the NF-C6P3 partial-entity defect (a board that still looks complete and is
 * quietly short). What is dropped here is visible: the caller renders "showing the top N of M".
 */
export function cheatSheet(board: Player[], doc: BigBoardDoc, limit: number): CheatSheetTier[] {
  const rows = applyDoc(board, doc)
  const tiers = customTiers(rows, doc)
  const moved = divergence(board, doc)
  const out: CheatSheetTier[] = []
  rows.slice(0, Math.max(0, limit)).forEach((p, i) => {
    const tier = tiers.get(p.id) ?? 1
    if (out.length === 0 || out[out.length - 1].tier !== tier) out.push({ tier, rows: [] })
    out[out.length - 1].rows.push({
      rank: i + 1,
      player: p,
      tag: doc.tags[p.id] ?? null,
      moved: moved.get(p.id) ?? 0,
      note: doc.notes?.[p.id] ?? null,
    })
  })
  return out
}
