"use client"

// NF3.1 — Player Search. The dedicated lookup surface every board's Player cell links out to
// (Projections, Rankings, League Board, Draft Optimizer) — a name in, a player page out. Kept
// separate from Projections' own in-table search box because it needs to be reachable on its own,
// not only as a side-effect of already being on another board.

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { Search } from "lucide-react"
import { useFantasyProjections } from "@/lib/fantasy-queries"
import {
  ALL_ROWS,
  ConfidenceBadge,
  EmptyBlock,
  LoadingBlock,
  Pagination,
  PosBadge,
  PositionTabs,
  ProvenanceLine,
  RookieBadge,
  SurfaceHeader,
  num,
  teamLabel,
} from "@/components/fantasy/shared"

export function PlayerSearch() {
  const { data, isLoading, error } = useFantasyProjections()
  const [pos, setPos] = useState("All")
  const [q, setQ] = useState("")
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState<number>(50)

  const players = data?.players ?? []

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return players
      .filter((p) => (pos === "All" ? true : p.pos === pos))
      .filter((p) => (needle ? p.name.toLowerCase().includes(needle) : true))
      .slice()
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [players, pos, q])

  const paged = useMemo(
    () => (pageSize === ALL_ROWS ? rows : rows.slice(page * pageSize, page * pageSize + pageSize)),
    [rows, page, pageSize],
  )

  useEffect(() => setPage(0), [pos, q])

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <SurfaceHeader
        title="Player Search"
        blurb="Look up any projected player by name to see his full page — raw stat line, fantasy points by format, the 80% range drawn, ADP and draft value."
      >
        <div className="mt-2">
          <ProvenanceLine
            season={data?.season ?? 2026}
            generatedAt={data?.generated_at}
            extra={data?.base_season ? `built off ${data.base_season} production` : null}
          />
        </div>
      </SurfaceHeader>

      {isLoading && <LoadingBlock label="Loading players…" />}

      {!isLoading && (error || players.length === 0) && (
        <EmptyBlock
          title="Player search isn't available yet"
          detail="The 2026 season projections haven't been published to this surface yet."
        />
      )}

      {!isLoading && players.length > 0 && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-500" />
              <input
                autoFocus
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search players…"
                className="w-64 rounded-md border border-[#262626] bg-[#111111] py-2 pl-8 pr-3 text-base text-white placeholder:text-gray-600 focus:border-[#363636] focus:outline-none"
              />
            </div>
            <PositionTabs value={pos} onChange={setPos} />
          </div>

          <div className="mb-3">
            <Pagination
              page={page}
              pageSize={pageSize}
              total={rows.length}
              onPage={setPage}
              onPageSize={setPageSize}
            />
          </div>

          {rows.length === 0 ? (
            <EmptyBlock
              title="No players match"
              detail="Try a different spelling, or clear the position filter."
            />
          ) : (
            <div className="space-y-1.5">
              {paged.map((p) => (
                <Link
                  key={p.id}
                  href={`/fantasy/player/${p.id}`}
                  className="flex items-center gap-3 rounded-lg border border-[#262626] bg-[#111111] px-4 py-3 transition-colors hover:border-[#363636] hover:bg-[#161616]"
                >
                  <PosBadge pos={p.pos} />
                  <div className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5">
                      <span className="truncate text-sm font-semibold text-white">{p.name}</span>
                      {p.rookie && <RookieBadge />}
                    </span>
                    <span className="text-xs text-gray-500">
                      {teamLabel(p)}
                      {p.bye != null ? ` · Bye ${p.bye}` : ""}
                    </span>
                  </div>
                  <div className="hidden text-right sm:block">
                    {/* ⚠️ THE ONE PROJECTED-POINTS SURFACE WITH NO TAPPABLE DEFINITION, and that is
                        deliberate rather than an oversight: this chip lives INSIDE the result's
                        `<Link>`, and `InfoTip` renders a real `<button>` — nesting one in an anchor
                        is invalid HTML and would make a tap on the definition navigate instead of
                        open. So the label alone carries the meaning here, and the full definition
                        is one tap away on the player page this row links to. */}
                    <span className="block text-[10px] uppercase tracking-wide text-gray-600">
                      Expected (PPR)
                    </span>
                    <span className="block text-sm font-semibold tabular-nums text-white">
                      {num(p.fpPpr)}
                    </span>
                  </div>
                  <ConfidenceBadge conf={p.conf} />
                </Link>
              ))}
            </div>
          )}

          <div className="mt-3">
            <Pagination
              page={page}
              pageSize={pageSize}
              total={rows.length}
              onPage={setPage}
              onPageSize={setPageSize}
            />
          </div>
        </>
      )}
    </div>
  )
}
