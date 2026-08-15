"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { format } from "date-fns"
import { CalendarIcon, Info, Search as SearchIcon, X as ClearIcon } from "lucide-react"
import { Nav } from "@/components/nav"
import { AuthGuard } from "@/components/auth-guard"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Input } from "@/components/ui/input"
import { Picker } from "@/components/ui/picker"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { useAuth } from "@/lib/auth-context"
import { useSelectedDate } from "@/lib/date-context"
import { apiFetch } from "@/lib/api"
import { LogPastPropDialog } from "@/components/log-past-prop-dialog"
import {
  buildGameGroups,
  buildGameMeta,
  distinctBooks,
  distinctLineValues,
  distinctTeams,
  filterRows,
  fmtGameTime,
  groupMatchesTeams,
  nextGameToStartPk,
  slateOrderCompare,
  sortOptionsFor,
  sortRowsByMetric,
  type SlateRow,
  type SlateSortKey,
} from "@/lib/props-slate"

// ---------------------------------------------------------------------------
// Prop types — extensible. Only Strikeouts (K) has a projection surface today; add more here as
// their models ship (each maps to its own index endpoint via `endpoint`).
// ---------------------------------------------------------------------------

type PropType = {
  key: string
  label: string
  endpoint: string
  available: boolean
}

const PROP_TYPES: PropType[] = [
  { key: "strikeouts", label: "Strikeouts (K)", endpoint: "/players/k-projections", available: true },
  // E5.9 — batter total-bases projections (model batter_tb_glm_nb_v1; regular season only).
  { key: "total_bases", label: "Total Bases (TB)", endpoint: "/players/tb-projections", available: true },
]

// ---------------------------------------------------------------------------
// Types — mirrors betting_ml/utils/k_projection_serving.build_index_payload / index_row
// ---------------------------------------------------------------------------

interface ProjectionRow {
  pitcher_id: number
  full_name: string | null
  team: string | null
  opponent: string | null
  game_pk: number | null
  game_date: string | null
  game_datetime: string | null
  last3_k: number[] | null
  mean: number | null
  median: number | null
  p10: number | null
  p90: number | null
  p05: number | null
  p95: number | null
  primary_line: number | null
  book_count: number
  // E5.10 — which sportsbooks quoted this pitcher at all (any line), sorted + deduped. Optional:
  // absent on an index row written before this field shipped (an older cached slate).
  books?: string[] | null
  model_p_over: number | null
  model_vs_book_p_over: number | null
  model_mean_minus_line: number | null
}

// E5.9 — mirrors betting_ml/utils/tb_projection_serving.index_row (batter TB tab)
interface BatterRow {
  batter_id: number
  full_name: string | null
  team: string | null
  opponent: string | null
  game_pk: number | null
  game_date: string | null
  game_datetime: string | null
  batting_slot: number | null
  mean: number | null
  median: number | null
  p10: number | null
  p90: number | null
  p05: number | null
  p95: number | null
  p_ge_2: number | null
  primary_line: number | null
  book_count: number
  // E5.10 — which sportsbooks quoted this batter at all (any line), sorted + deduped. Optional:
  // absent on an index row written before this field shipped (an older cached slate).
  books?: string[] | null
  model_p_over: number | null
  model_vs_book_p_over: number | null
  model_mean_minus_line: number | null
}

interface ProjectionIndex {
  game_date: string | null
  count: number
  pitchers?: ProjectionRow[]
  batters?: BatterRow[]
  disclaimer?: string
  best_alpha?: number
  is_bet_recommendation?: boolean
}

const DISCLAIMER_FALLBACK =
  "Projections reflect our model; they are not betting advice and we make no profitability claim. " +
  "Single-game strikeout totals are high-variance — treat this as informational context, not a play."

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtSignedPct(p: number | null): string {
  if (p == null) return "—"
  const v = p * 100
  return `${v >= 0 ? "+" : ""}${v.toFixed(0)} pts`
}

// Compact range bar: 5th–95th band, 80% (p10–p90) emphasis, median tick, book-line marker.
function MiniRange({ r }: { r: ProjectionRow }) {
  const p05 = r.p05
  const p95 = r.p95
  if (p05 == null || p95 == null) return null
  const line = r.primary_line
  const lo = Math.min(p05, line ?? p05) - 1
  const hi = Math.max(p95, line ?? p95) + 1
  const span = Math.max(hi - lo, 1)
  const pos = (v: number) => ((v - lo) / span) * 100

  return (
    <div className="relative mt-3 h-6">
      <div
        className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-[#1f2937]"
        style={{ left: `${pos(p05)}%`, width: `${pos(p95) - pos(p05)}%` }}
      />
      {r.p10 != null && r.p90 != null && (
        <div
          className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-emerald-500/40"
          style={{ left: `${pos(r.p10)}%`, width: `${pos(r.p90) - pos(r.p10)}%` }}
        />
      )}
      {r.median != null && (
        <div
          className="absolute top-1/2 h-4 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded bg-emerald-400"
          style={{ left: `${pos(r.median)}%` }}
          title={`Projected median: ${r.median} K`}
        />
      )}
      {line != null && (
        <div
          className="absolute top-1/2 h-5 w-[2px] -translate-x-1/2 -translate-y-1/2 bg-amber-400/90"
          style={{ left: `${pos(line)}%` }}
          title={`Book line: ${line}`}
        />
      )}
    </div>
  )
}

function ProjectionCard({ r }: { r: ProjectionRow }) {
  return (
    <Link
      href={r.game_date ? `/props/${r.pitcher_id}?as_of=${r.game_date}` : `/props/${r.pitcher_id}`}
      data-testid="props-card"
      data-books={(r.books ?? []).join(",")}
      className="block rounded-lg border border-[#262626] bg-[#111111] p-4 transition-colors hover:border-[#3a3a3a] hover:bg-[#141414]"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div data-testid="props-card-name" className="truncate font-semibold text-white">
            {r.full_name ?? `Pitcher ${r.pitcher_id}`}
          </div>
          <div className="truncate text-[11px]">
            <span className="font-medium text-gray-200">{r.team ?? "—"}</span>
            {r.opponent ? <span className="text-gray-600"> vs {r.opponent}</span> : null}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-wider text-gray-500">Proj K</div>
          <div
            data-testid="props-card-proj"
            data-proj={r.mean ?? ""}
            className="text-2xl font-bold tabular-nums text-emerald-400"
          >
            {r.mean != null ? r.mean.toFixed(1) : "—"}
          </div>
          {fmtGameTime(r.game_datetime) && (
            <div className="text-[10px] text-gray-500">{fmtGameTime(r.game_datetime)}</div>
          )}
        </div>
      </div>

      {r.last3_k && r.last3_k.length > 0 && (
        <div className="mt-2 flex items-center gap-1.5 text-[10px] text-gray-500">
          <span className="uppercase tracking-wider text-gray-600">Last 3 K</span>
          {r.last3_k.map((k, i) => (
            <span key={i} className="rounded bg-[#1a1a1a] px-1.5 py-0.5 tabular-nums text-gray-300">
              {k}
            </span>
          ))}
        </div>
      )}

      <MiniRange r={r} />

      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-600">80% range</div>
          <div className="text-xs tabular-nums text-gray-300">
            {r.p10 != null && r.p90 != null ? `${r.p10}–${r.p90}` : "—"}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-600">Book line</div>
          <div
            data-testid="props-card-line"
            data-line={r.primary_line ?? ""}
            className="text-xs tabular-nums text-amber-400"
          >
            {r.primary_line != null ? r.primary_line : "—"}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-600">Model − Book</div>
          <div
            data-testid="props-card-diff"
            data-diff={r.model_vs_book_p_over ?? ""}
            className={`text-xs tabular-nums ${
              (r.model_vs_book_p_over ?? 0) >= 0 ? "text-emerald-400" : "text-gray-400"
            }`}
          >
            {r.model_vs_book_p_over != null ? fmtSignedPct(r.model_vs_book_p_over) : "—"}
          </div>
        </div>
      </div>
    </Link>
  )
}

// E5.9 — batter TB card (the Total Bases tab). Same furniture as the pitcher card so the two
// tabs read as one surface; the headline is the projected TB mean + the P(2+ bases) chip.
function BatterProjectionCard({ r }: { r: BatterRow }) {
  const p05 = r.p05
  const p95 = r.p95
  const line = r.primary_line
  const lo = p05 != null ? Math.min(p05, line ?? p05) - 1 : 0
  const hi = p95 != null ? Math.max(p95, line ?? p95) + 1 : 1
  const span = Math.max(hi - lo, 1)
  const pos = (v: number) => ((v - lo) / span) * 100

  return (
    <Link
      href={
        r.game_date ? `/props/batter/${r.batter_id}?as_of=${r.game_date}` : `/props/batter/${r.batter_id}`
      }
      data-testid="props-card"
      data-books={(r.books ?? []).join(",")}
      className="block rounded-lg border border-[#262626] bg-[#111111] p-4 transition-colors hover:border-[#3a3a3a] hover:bg-[#141414]"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div data-testid="props-card-name" className="truncate font-semibold text-white">
            {r.full_name ?? `Batter ${r.batter_id}`}
          </div>
          <div className="truncate text-[11px]">
            <span className="font-medium text-gray-200">{r.team ?? "—"}</span>
            {r.opponent ? <span className="text-gray-600"> vs {r.opponent}</span> : null}
            {r.batting_slot != null ? (
              <span className="text-gray-600"> · batting {r.batting_slot}</span>
            ) : null}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-wider text-gray-500">Proj TB</div>
          <div
            data-testid="props-card-proj"
            data-proj={r.mean ?? ""}
            className="text-2xl font-bold tabular-nums text-emerald-400"
          >
            {r.mean != null ? r.mean.toFixed(1) : "—"}
          </div>
          {fmtGameTime(r.game_datetime) && (
            <div className="text-[10px] text-gray-500">{fmtGameTime(r.game_datetime)}</div>
          )}
        </div>
      </div>

      {p05 != null && p95 != null && (
        <div className="relative mt-3 h-6">
          <div
            className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-[#1f2937]"
            style={{ left: `${pos(p05)}%`, width: `${pos(p95) - pos(p05)}%` }}
          />
          {r.p10 != null && r.p90 != null && (
            <div
              className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-emerald-500/40"
              style={{ left: `${pos(r.p10)}%`, width: `${pos(r.p90) - pos(r.p10)}%` }}
            />
          )}
          {r.median != null && (
            <div
              className="absolute top-1/2 h-4 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded bg-emerald-400"
              style={{ left: `${pos(r.median)}%` }}
              title={`Projected median: ${r.median} TB`}
            />
          )}
          {line != null && (
            <div
              className="absolute top-1/2 h-5 w-[2px] -translate-x-1/2 -translate-y-1/2 bg-amber-400/90"
              style={{ left: `${pos(line)}%` }}
              title={`Book line: ${line}`}
            />
          )}
        </div>
      )}

      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-600">P(2+ bases)</div>
          <div data-testid="props-card-p2" data-p2={r.p_ge_2 ?? ""} className="text-xs tabular-nums text-gray-300">
            {r.p_ge_2 != null ? `${(r.p_ge_2 * 100).toFixed(0)}%` : "—"}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-600">Book line</div>
          <div
            data-testid="props-card-line"
            data-line={r.primary_line ?? ""}
            className="text-xs tabular-nums text-amber-400"
          >
            {r.primary_line != null ? r.primary_line : "—"}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-600">Model − Book</div>
          <div
            data-testid="props-card-diff"
            data-diff={r.model_vs_book_p_over ?? ""}
            className={`text-xs tabular-nums ${
              (r.model_vs_book_p_over ?? 0) >= 0 ? "text-emerald-400" : "text-gray-400"
            }`}
          >
            {r.model_vs_book_p_over != null ? fmtSignedPct(r.model_vs_book_p_over) : "—"}
          </div>
        </div>
      </div>
    </Link>
  )
}

// ---------------------------------------------------------------------------
// E5.10 — slate navigation: search, sort, filter chips.
// ---------------------------------------------------------------------------

function FilterChip({
  label,
  active,
  onClick,
  testId,
  capitalizeLabel,
}: {
  label: string
  active: boolean
  onClick: () => void
  testId: string
  /** The raw book key ("bovada") is what's matched on; capitalize only how it's DISPLAYED — the
   *  same `capitalize` CSS convention the per-book table on the detail page already uses. */
  capitalizeLabel?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      aria-pressed={active}
      className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
        capitalizeLabel ? "capitalize" : ""
      } ${
        active
          ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-300"
          : "border-[#262626] bg-[#111111] text-gray-400 hover:border-[#3a3a3a] hover:text-gray-200"
      }`}
    >
      {label}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function PropsPageInner() {
  const { accessToken, email } = useAuth()
  // Shared slate date — held in the same context as the other betting pages, so the selected day
  // carries across pages.
  const { selectedDate, setSelectedDate, isoDate } = useSelectedDate()
  const [propType, setPropType] = useState<string>(PROP_TYPES[0].key)
  const [calOpen, setCalOpen] = useState(false)

  // ── E5.10 slate-navigation state ──────────────────────────────────────────────────────────────
  const [search, setSearch] = useState("")
  const [sortKey, setSortKey] = useState<SlateSortKey>("slate")
  const [selectedTeams, setSelectedTeams] = useState<Set<string>>(new Set())
  const [lineFilter, setLineFilter] = useState<number | null>(null)
  const [minBookCount, setMinBookCount] = useState<number | null>(null)
  const [selectedBooks, setSelectedBooks] = useState<Set<string>>(new Set())
  const [openGroups, setOpenGroups] = useState<string[]>([])
  const [initializedSlateKey, setInitializedSlateKey] = useState<string | null>(null)

  const active = PROP_TYPES.find((p) => p.key === propType) ?? PROP_TYPES[0]
  const isBatterTab = active.key === "total_bases"

  const { data, isLoading, isError } = useQuery<ProjectionIndex>({
    queryKey: ["props-index", active.key, isoDate],
    queryFn: () => apiFetch(`${active.endpoint}?as_of=${isoDate}`, {}, accessToken!),
    enabled: !!accessToken && active.available,
    staleTime: 1000 * 60 * 30,
  })

  // Original per-tab rows, keyed by id, so a card can render its full field set (last3_k, p10/p90,
  // batting slot, …) after the slate-nav logic below has reduced everything to the common shape.
  const originalById = useMemo(() => {
    const map = new Map<number, BatterRow | ProjectionRow>()
    if (isBatterTab) {
      for (const r of data?.batters ?? []) map.set(r.batter_id, r)
    } else {
      for (const r of data?.pitchers ?? []) map.set(r.pitcher_id, r)
    }
    return map
  }, [data, isBatterTab])

  // Mapped once into the tab-agnostic shape every group/search/sort/filter function operates on
  // (frontend/lib/props-slate.ts) — both tabs go through the SAME logic here.
  const rows: SlateRow[] = useMemo(() => {
    if (isBatterTab) {
      return (data?.batters ?? []).map((r) => ({
        id: r.batter_id,
        fullName: r.full_name,
        team: r.team,
        opponent: r.opponent,
        gamePk: r.game_pk,
        gameDatetime: r.game_datetime,
        order: r.batting_slot ?? 10,
        proj: r.mean,
        pGe2: r.p_ge_2,
        line: r.primary_line,
        bookCount: r.book_count,
        diff: r.model_vs_book_p_over,
        books: r.books ?? [],
      }))
    }
    return (data?.pitchers ?? []).map((r, i) => ({
      id: r.pitcher_id,
      fullName: r.full_name,
      team: r.team,
      opponent: r.opponent,
      gamePk: r.game_pk,
      gameDatetime: r.game_datetime,
      order: i,
      proj: r.mean,
      pGe2: null,
      line: r.primary_line,
      bookCount: r.book_count,
      diff: r.model_vs_book_p_over,
      books: r.books ?? [],
    }))
  }, [data, isBatterTab])

  const cardCount = rows.length
  const gameMeta = useMemo(() => buildGameMeta(rows), [rows])
  const allGroups = useMemo(() => buildGameGroups(rows, gameMeta), [rows, gameMeta])

  const teamsAll = useMemo(() => distinctTeams(rows), [rows])
  const lineValuesAll = useMemo(() => distinctLineValues(rows), [rows])
  const maxBookCount = useMemo(() => rows.reduce((m, r) => Math.max(m, r.bookCount), 0), [rows])
  const bookCountThresholds = useMemo(() => [2, 3].filter((n) => n <= maxBookCount), [maxBookCount])
  // E5.10 — every sportsbook that quoted anything on this slate, e.g. so a Bovada bettor can
  // filter straight to the props their own book actually posted a line for.
  const sportsbooksAll = useMemo(() => distinctBooks(rows), [rows])

  // A new tab or a new date is a fresh slate: reset search/sort/filters, and default to the next
  // game to start (collapsed elsewhere). Guarded so a background react-query refetch of the SAME
  // slate never clobbers what the visitor already typed/clicked.
  const slateKey = `${active.key}|${isoDate}`
  useEffect(() => {
    if (initializedSlateKey === slateKey) return
    setSearch("")
    setSortKey("slate")
    setSelectedTeams(new Set())
    setLineFilter(null)
    setMinBookCount(null)
    setSelectedBooks(new Set())
    if (allGroups.length > 0) {
      const next = nextGameToStartPk(allGroups, Date.now())
      setOpenGroups(next != null ? [String(next)] : [])
      setInitializedSlateKey(slateKey)
    } else {
      setOpenGroups([])
    }
  }, [slateKey, allGroups, initializedSlateKey])

  const filteredRows = useMemo(
    () => filterRows(rows, { search, line: lineFilter, minBookCount, books: selectedBooks }),
    [rows, search, lineFilter, minBookCount, selectedBooks],
  )
  const visibleRows = useMemo(
    () =>
      filteredRows.filter((r) => {
        if (r.gamePk == null) return selectedTeams.size === 0
        return groupMatchesTeams(gameMeta.get(r.gamePk)?.teams ?? [], selectedTeams)
      }),
    [filteredRows, gameMeta, selectedTeams],
  )

  const groups = useMemo(() => {
    const built = buildGameGroups(visibleRows, gameMeta)
    return built.map((g) => ({ ...g, rows: [...g.rows].sort(slateOrderCompare) }))
  }, [visibleRows, gameMeta])

  const flatSorted = useMemo(() => {
    if (sortKey === "slate") return []
    return sortRowsByMetric(visibleRows, sortKey)
  }, [visibleRows, sortKey])

  const filtersActive =
    !!search.trim() ||
    selectedTeams.size > 0 ||
    lineFilter != null ||
    minBookCount != null ||
    selectedBooks.size > 0
  const effectiveOpenValues = filtersActive ? groups.map((g) => String(g.gamePk)) : openGroups

  const projLabel = isBatterTab ? "Proj TB" : "Proj K"
  const sortOptions = useMemo(() => sortOptionsFor(isBatterTab, projLabel), [isBatterTab, projLabel])

  function toggleTeam(team: string) {
    setSelectedTeams((prev) => {
      const next = new Set(prev)
      if (next.has(team)) next.delete(team)
      else next.add(team)
      return next
    })
  }

  function toggleBook(book: string) {
    setSelectedBooks((prev) => {
      const next = new Set(prev)
      if (next.has(book)) next.delete(book)
      else next.add(book)
      return next
    })
  }

  function clearFilters() {
    setSearch("")
    setSelectedTeams(new Set())
    setLineFilter(null)
    setMinBookCount(null)
    setSelectedBooks(new Set())
  }

  function renderCard(id: number) {
    const orig = originalById.get(id)
    if (!orig) return null
    return isBatterTab ? (
      <BatterProjectionCard key={id} r={orig as BatterRow} />
    ) : (
      <ProjectionCard key={id} r={orig as ProjectionRow} />
    )
  }

  return (
    <>
      <Nav authenticated activeLink="props" userEmail={email} />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <h1 className="mb-1 text-2xl font-bold text-white">Props</h1>
        <p className="mb-5 max-w-3xl text-sm text-gray-500">
          {isBatterTab
            ? "Our model's total-bases projection for each batter with a posted line, shown next to " +
              "the sportsbooks' line. Projections and a transparency comparison only — click a batter " +
              "for the full distribution and per-book breakdown."
            : "Our model's projection for each probable starter, shown next to the sportsbooks' " +
              "posted line. Projections and a transparency comparison only — click a pitcher for the " +
              "full distribution and per-book breakdown."}
        </p>

        {/* Prop-type + date controls */}
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <div className="inline-flex rounded-md border border-[#262626] bg-[#111111] p-0.5">
              {PROP_TYPES.map((p) => (
                <button
                  key={p.key}
                  onClick={() => p.available && setPropType(p.key)}
                  disabled={!p.available}
                  className={`rounded px-3 py-1.5 text-sm font-medium transition-colors ${
                    p.key === propType
                      ? "bg-[#1a1a1a] text-white"
                      : p.available
                        ? "text-gray-500 hover:text-gray-300"
                        : "cursor-not-allowed text-gray-700"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <span className="hidden text-[11px] text-gray-600 sm:inline">More prop types coming soon</span>
          </div>

          <div className="flex items-center gap-2">
          {/* Log a strikeout prop you placed (any game in the last ~14 days) straight into your Bet Log —
              a bookkeeping convenience, works even for past dates with no projection here. */}
          <LogPastPropDialog initialDate={selectedDate} />

          {/* Date picker — the same shared control the other betting pages use */}
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
                onSelect={(d) => {
                  if (d) {
                    setSelectedDate(d)
                    setCalOpen(false)
                  }
                }}
                toDate={new Date()}
                initialFocus
              />
            </PopoverContent>
          </Popover>
          </div>
        </div>

        {/* E5.10 — slate navigation: search, sort, filter chips. Only once there is a slate to
            navigate; the loading/error/empty states below are unaffected. */}
        {!isLoading && !isError && cardCount > 0 && (
          <div className="mb-4 flex flex-col gap-3 rounded-lg border border-[#1e1e1e] bg-[#0b0b0b] p-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="relative w-full sm:max-w-xs">
                <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-600" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={isBatterTab ? "Search batters" : "Search pitchers"}
                  aria-label={isBatterTab ? "Search batters by name" : "Search pitchers by name"}
                  data-testid="props-search"
                  className="h-9 border-[#262626] bg-[#141414] pl-8 text-white placeholder:text-gray-600"
                />
              </div>

              <div className="flex items-center gap-2">
                <label htmlFor="props-sort" className="text-[11px] uppercase tracking-wider text-gray-600">
                  Sort
                </label>
                <Picker
                  id="props-sort"
                  ariaLabel="Sort"
                  value={sortKey}
                  onValueChange={(v) => setSortKey(v as SlateSortKey)}
                  options={sortOptions.map((o) => ({ value: o.key, label: o.label }))}
                  className="h-9 w-[180px] border-[#262626] bg-[#141414] text-sm text-white"
                  contentClassName="border-[#262626] bg-[#141414] text-white"
                />
              </div>
            </div>

            {/* Filter chips — one category per row (E5.10 follow-up: previously all four
                categories shared a single flex-wrap row and ran together whenever the chips
                overflowed, reading as one messy jumble instead of four distinct filters). */}
            <div className="flex flex-col gap-2">
              {teamsAll.length > 1 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="w-[92px] shrink-0 text-[11px] uppercase tracking-wider text-gray-600">
                    Team
                  </span>
                  {teamsAll.map((t) => (
                    <FilterChip
                      key={t}
                      label={t}
                      active={selectedTeams.has(t)}
                      onClick={() => toggleTeam(t)}
                      testId={`props-filter-team-${t}`}
                    />
                  ))}
                </div>
              )}
              {lineValuesAll.length > 1 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="w-[92px] shrink-0 text-[11px] uppercase tracking-wider text-gray-600">
                    Line
                  </span>
                  {lineValuesAll.map((l) => (
                    <FilterChip
                      key={l}
                      label={String(l)}
                      active={lineFilter === l}
                      onClick={() => setLineFilter((prev) => (prev === l ? null : l))}
                      testId={`props-filter-line-${l}`}
                    />
                  ))}
                </div>
              )}
              {bookCountThresholds.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="w-[92px] shrink-0 text-[11px] uppercase tracking-wider text-gray-600">
                    Min. books
                  </span>
                  {bookCountThresholds.map((n) => (
                    <FilterChip
                      key={n}
                      label={`${n}+`}
                      active={minBookCount === n}
                      onClick={() => setMinBookCount((prev) => (prev === n ? null : n))}
                      testId={`props-filter-books-${n}`}
                    />
                  ))}
                </div>
              )}
              {sportsbooksAll.length > 1 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="w-[92px] shrink-0 text-[11px] uppercase tracking-wider text-gray-600">
                    Sportsbook
                  </span>
                  {sportsbooksAll.map((b) => (
                    <FilterChip
                      key={b}
                      label={b}
                      capitalizeLabel
                      active={selectedBooks.has(b)}
                      onClick={() => toggleBook(b)}
                      testId={`props-filter-book-${b}`}
                    />
                  ))}
                </div>
              )}
              {filtersActive && (
                <button
                  type="button"
                  onClick={clearFilters}
                  data-testid="props-clear-filters"
                  className="inline-flex w-fit items-center gap-1 text-[11px] text-gray-500 hover:text-gray-300"
                >
                  <ClearIcon className="h-3 w-3" />
                  Clear filters
                </button>
              )}
            </div>
          </div>
        )}

        {isLoading ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-40 w-full rounded-lg" />
            ))}
          </div>
        ) : isError ? (
          <div className="rounded-lg border border-[#262626] bg-[#111111] px-4 py-8 text-center text-sm text-gray-500">
            Couldn&apos;t load projections right now. Please try again shortly.
          </div>
        ) : cardCount === 0 ? (
          <div className="rounded-lg border border-[#262626] bg-[#111111] px-4 py-10 text-center">
            <p className="text-sm text-gray-400">
              No projections for {format(selectedDate, "MMM d, yyyy")} yet.
            </p>
            <p className="mt-1 text-xs text-gray-600">
              {isBatterTab
                ? "Total-bases projections appear once sportsbooks post batter lines for the day's " +
                  "slate (regular-season games only). Try another date."
                : "Projections appear once probable starters are announced for the day's slate. Try " +
                  'another date. To record a prop you placed on a past game, use "Log a prop" above.'}
            </p>
          </div>
        ) : visibleRows.length === 0 ? (
          <div
            data-testid="props-no-results"
            className="rounded-lg border border-[#262626] bg-[#111111] px-4 py-10 text-center"
          >
            <p className="text-sm text-gray-400">No {isBatterTab ? "batters" : "pitchers"} match your filters.</p>
            <button
              type="button"
              onClick={clearFilters}
              className="mt-2 text-xs text-emerald-400 hover:text-emerald-300"
            >
              Clear filters
            </button>
          </div>
        ) : sortKey === "slate" ? (
          <div data-testid="props-game-groups">
            <Accordion
              type="multiple"
              value={effectiveOpenValues}
              onValueChange={setOpenGroups}
              className="flex flex-col gap-2"
            >
              {groups.map((g) => (
                <AccordionItem
                  key={g.gamePk}
                  value={String(g.gamePk)}
                  data-testid="props-game-group"
                  data-game-pk={g.gamePk}
                  className="rounded-lg border border-[#262626] bg-[#0d0d0d] px-3"
                >
                  <AccordionTrigger data-testid="props-game-header" className="py-3 text-sm hover:no-underline">
                    <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                      <span className="font-semibold text-white">{g.label}</span>
                      {fmtGameTime(g.rows[0]?.gameDatetime ?? null) && (
                        <span className="text-xs text-gray-500">{fmtGameTime(g.rows[0]?.gameDatetime ?? null)}</span>
                      )}
                      <span className="text-xs text-gray-600">
                        · {g.rows.length} {isBatterTab ? "batter" : "pitcher"}
                        {g.rows.length === 1 ? "" : "s"}
                      </span>
                    </span>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="grid gap-3 pb-1 sm:grid-cols-2 lg:grid-cols-3">
                      {g.rows.map((r) => renderCard(r.id))}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </div>
        ) : (
          <div data-testid="props-flat-list" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {flatSorted.map((r) => renderCard(r.id))}
          </div>
        )}

        {/* Honest-framing disclaimer */}
        <div className="mt-6 flex items-start gap-2 rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-3 py-2.5">
          <Info className="mt-0.5 h-3 w-3 shrink-0 text-gray-600" />
          <p className="text-[11px] leading-relaxed text-gray-500">
            {data?.disclaimer || DISCLAIMER_FALLBACK}
          </p>
        </div>
      </main>
    </>
  )
}

export default function PropsPage() {
  return (
    <AuthGuard>
      <PropsPageInner />
    </AuthGuard>
  )
}
