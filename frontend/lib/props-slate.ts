// E5.10 — /props slate navigation: group-by-game, search, sort, filter-chip logic.
//
// Pure and API-shape-agnostic on purpose. The page maps its two row shapes (pitcher K rows, batter
// TB rows) into the one `SlateRow` here, so every function below runs identically for both tabs —
// the story's "apply everything to BOTH tabs, it's one product" rule enforced by construction
// rather than by two parallel implementations that could drift.

export type SlateSortKey = "slate" | "proj" | "p2" | "diff"

export interface SlateSortOption {
  key: SlateSortKey
  label: string
}

// ⭐ PM ruling (honest-framing, hard): "difference vs books" is a legitimate sort — the delta is
// already-displayed transparency — but it is NEVER the default sort and its label stays
// descriptive, never "top plays" / "best" / any editorial framing. `claim-denylist.ts` screens
// every rendered string (including this one) so a future copy edit can't drift toward one.
export const DIFF_VS_BOOKS_LABEL = "Difference vs books"
export const SLATE_ORDER_LABEL = "Slate order"

/** Sort options for one tab. `hasP2` is false for the pitcher (K) tab — there is no P(2+) there. */
export function sortOptionsFor(hasP2: boolean, projLabel: string): SlateSortOption[] {
  const opts: SlateSortOption[] = [
    { key: "slate", label: SLATE_ORDER_LABEL },
    { key: "proj", label: projLabel },
  ]
  if (hasP2) opts.push({ key: "p2", label: "P(2+)" })
  opts.push({ key: "diff", label: DIFF_VS_BOOKS_LABEL })
  return opts
}

export interface SlateRow {
  id: number
  fullName: string | null
  team: string | null
  opponent: string | null
  gamePk: number | null
  gameDatetime: string | null
  /** Lineup slot for a batter; a stable tiebreaker for a pitcher (there is no batting order). */
  order: number
  proj: number | null
  pGe2: number | null
  line: number | null
  bookCount: number
  diff: number | null
}

// First-pitch instant (ms) for sorting/grouping; same "treat as UTC if no tz suffix" rule the
// card display uses. Missing/unparseable times sort last.
export function gameTimeMs(raw: string | null): number {
  if (!raw) return Infinity
  const iso = raw.endsWith("Z") || /[+-]\d\d:?\d\d$/.test(raw) ? raw : raw + "Z"
  const t = new Date(iso).getTime()
  return Number.isNaN(t) ? Infinity : t
}

export function fmtGameTime(raw: string | null): string | null {
  if (!raw) return null
  const iso = raw.endsWith("Z") || /[+-]\d\d:?\d\d$/.test(raw) ? raw : raw + "Z"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
}

export interface GameGroup {
  gamePk: number
  label: string
  timeMs: number
  teams: string[]
  rows: SlateRow[]
}

/** One label per game_pk built from whatever rows carry it — team codes alphabetized so the
 *  label is deterministic regardless of which side's rows happen to be present/filtered. */
function labelFor(teams: string[], fallbackOpponent: string | null): string {
  if (teams.length >= 2) return teams.join(" vs ")
  if (teams.length === 1) return fallbackOpponent ? `${teams[0]} vs ${fallbackOpponent}` : teams[0]
  return "Unknown matchup"
}

/** Group metadata for EVERY game in `rows`, keyed by game_pk. Built once from the unfiltered row
 *  set so a game's identity (teams/time/label) survives any row-level filter trimming its rows —
 *  a team chip should still find the game even if a line/search filter emptied one side of it. */
export function buildGameMeta(rows: SlateRow[]): Map<number, { label: string; timeMs: number; teams: string[] }> {
  const byGame = new Map<number, SlateRow[]>()
  for (const r of rows) {
    if (r.gamePk == null) continue
    if (!byGame.has(r.gamePk)) byGame.set(r.gamePk, [])
    byGame.get(r.gamePk)!.push(r)
  }
  const meta = new Map<number, { label: string; timeMs: number; teams: string[] }>()
  for (const [gamePk, groupRows] of byGame) {
    const teams = Array.from(new Set(groupRows.map((r) => r.team).filter((t): t is string => !!t))).sort()
    const timeMs = Math.min(...groupRows.map((r) => gameTimeMs(r.gameDatetime)))
    meta.set(gamePk, { label: labelFor(teams, groupRows[0]?.opponent ?? null), timeMs, teams })
  }
  return meta
}

/** Group `rows` (already row-filtered) by game_pk, using `meta` for label/time/team identity so
 *  the group survives even when a filter has trimmed it down to one side's rows. Sorted by
 *  first-pitch time ascending, then game_pk. */
export function buildGameGroups(
  rows: SlateRow[],
  meta: Map<number, { label: string; timeMs: number; teams: string[] }>,
): GameGroup[] {
  const byGame = new Map<number, SlateRow[]>()
  for (const r of rows) {
    if (r.gamePk == null) continue
    if (!byGame.has(r.gamePk)) byGame.set(r.gamePk, [])
    byGame.get(r.gamePk)!.push(r)
  }
  const groups: GameGroup[] = []
  for (const [gamePk, groupRows] of byGame) {
    const m = meta.get(gamePk)
    if (!m) continue
    groups.push({ gamePk, label: m.label, timeMs: m.timeMs, teams: m.teams, rows: groupRows })
  }
  groups.sort((a, b) => a.timeMs - b.timeMs || a.gamePk - b.gamePk)
  return groups
}

/** The game_pk of the next game to start (earliest first-pitch at/after `nowMs`), falling back to
 *  the earliest game of the slate if every game has already started (e.g. viewing a past date). */
export function nextGameToStartPk(groups: GameGroup[], nowMs: number): number | null {
  if (!groups.length) return null
  const future = groups.filter((g) => g.timeMs >= nowMs)
  return (future[0] ?? groups[0]).gamePk
}

export function matchesSearch(row: SlateRow, search: string): boolean {
  const q = search.trim().toLowerCase()
  if (!q) return true
  return (row.fullName ?? "").toLowerCase().includes(q)
}

export interface RowFilters {
  search: string
  line: number | null
  minBookCount: number | null
}

/** Row-level filters only — search, line value, min book count. Team/matchup filtering is
 *  group-level (see `groupMatchesTeams`) because it narrows to a MATCHUP, not to one side's rows. */
export function filterRows(rows: SlateRow[], f: RowFilters): SlateRow[] {
  return rows.filter(
    (r) =>
      matchesSearch(r, f.search) &&
      (f.line == null || r.line === f.line) &&
      (f.minBookCount == null || r.bookCount >= f.minBookCount),
  )
}

export function distinctLineValues(rows: SlateRow[]): number[] {
  return Array.from(new Set(rows.map((r) => r.line).filter((l): l is number => l != null))).sort(
    (a, b) => a - b,
  )
}

export function distinctTeams(rows: SlateRow[]): string[] {
  return Array.from(new Set(rows.map((r) => r.team).filter((t): t is string => !!t))).sort()
}

/** A game qualifies for a team/matchup chip selection if EITHER side is a selected team — an
 *  empty selection matches every game (no filter applied). */
export function groupMatchesTeams(teams: string[], selected: Set<string>): boolean {
  if (selected.size === 0) return true
  return teams.some((t) => selected.has(t))
}

/** Descending by the chosen metric; a row missing that metric sorts last. "slate" order is NOT
 *  handled here — the caller renders the grouped view for it instead of a flat sorted list. */
export function sortRowsByMetric(rows: SlateRow[], key: Exclude<SlateSortKey, "slate">): SlateRow[] {
  const metric = (r: SlateRow): number => {
    const v = key === "proj" ? r.proj : key === "p2" ? r.pGe2 : r.diff
    return v == null ? -Infinity : v
  }
  return [...rows].sort((a, b) => metric(b) - metric(a))
}

/** Slate-order comparator: first pitch ascending, then game_pk, then lineup/order within a game. */
export function slateOrderCompare(a: SlateRow, b: SlateRow): number {
  const ta = gameTimeMs(a.gameDatetime)
  const tb = gameTimeMs(b.gameDatetime)
  if (ta !== tb) return ta - tb
  if ((a.gamePk ?? 0) !== (b.gamePk ?? 0)) return (a.gamePk ?? 0) - (b.gamePk ?? 0)
  return a.order - b.order
}
