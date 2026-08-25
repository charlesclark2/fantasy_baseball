"use client"

// NCAAF-P3.2 — the headline. The P3 brand directive's first clause is "lead with the WIN
// PROBABILITY (both sides, '58% / 42%')", so this is the largest thing on a card.
//
// ⛔ BOTH SIDES COME FROM THE PAYLOAD. `away` is served explicitly and is NOT computed as
// `1 - home` here: two renderers of one number is how they drift (E9.61), and the server already
// did the arithmetic. If the payload carries one side and not the other, that is what renders —
// inventing the missing half would be presenting a number nobody produced.

import { WIN_PROBABILITY_ABSENT, WIN_PROBABILITY_HINT, WIN_PROBABILITY_LABEL } from "@/lib/ncaaf-copy"
import type { NcaafWinProbability } from "@/lib/ncaaf"

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v)

/** One decimal place is noise on a probability read off 20,000 draws; a whole percent is the
 *  honest resolution and is what the directive's own example ("58% / 42%") is written in. */
export const formatProbability = (p: number | null | undefined) =>
  isNum(p) ? `${Math.round(p * 100)}%` : "—"

export function WinProbability({
  winProbability,
  homeTeam,
  awayTeam,
  testId = "ncaaf-win-probability",
}: {
  winProbability: NcaafWinProbability
  homeTeam: string
  awayTeam: string
  testId?: string
}) {
  const home = isNum(winProbability.home) ? winProbability.home : null
  const away = isNum(winProbability.away) ? winProbability.away : null

  if (home === null && away === null) {
    return (
      <div data-testid={testId} data-win-probability="absent" className="space-y-1">
        <div className="text-[10px] uppercase tracking-widest text-gray-500">
          {WIN_PROBABILITY_LABEL}
        </div>
        <p className="text-xs text-gray-500">{WIN_PROBABILITY_ABSENT}</p>
      </div>
    )
  }

  // The split bar. Widths come from the SERVED pair, so a payload whose two sides do not sum to 1
  // renders as it is rather than being silently normalised into agreement — a disagreement between
  // the two served numbers is a data fact, and hiding it would hide it from us too.
  const total = (home ?? 0) + (away ?? 0)
  const awayWidth = total > 0 ? ((away ?? 0) / total) * 100 : 50

  return (
    <div data-testid={testId} data-win-probability="present" className="space-y-1.5">
      <div className="text-[10px] uppercase tracking-widest text-gray-500">
        {WIN_PROBABILITY_LABEL}
      </div>
      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-xs text-gray-400">{awayTeam}</div>
          <div data-testid={`${testId}-away`} className="text-2xl font-semibold tabular-nums text-white">
            {formatProbability(away)}
          </div>
        </div>
        <div className="min-w-0 text-right">
          <div className="truncate text-xs text-gray-400">{homeTeam}</div>
          <div data-testid={`${testId}-home`} className="text-2xl font-semibold tabular-nums text-white">
            {formatProbability(home)}
          </div>
        </div>
      </div>
      <div
        className="flex h-2 w-full overflow-hidden rounded-full bg-[#1e1e1e]"
        role="img"
        aria-label={`${awayTeam} ${formatProbability(away)}, ${homeTeam} ${formatProbability(home)}`}
      >
        <div className="h-full bg-sky-500/70" style={{ width: `${awayWidth}%` }} />
        <div className="h-full bg-emerald-500/70" style={{ width: `${100 - awayWidth}%` }} />
      </div>
      <p className="text-[11px] leading-snug text-gray-500">{WIN_PROBABILITY_HINT}</p>
    </div>
  )
}
