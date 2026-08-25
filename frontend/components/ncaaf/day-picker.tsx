"use client"

// NCAAF-P3.2 — the "week selector", which is a KICKOFF-DAY selector and the naming is load-bearing.
//
// ⛔ THERE IS NO WEEK PARAMETER AND THERE WILL NOT BE ONE. CFBD restarts `week` at 1 for the
// postseason, so "week 1" names both the season opener and a December bowl; `game_prediction_
// snapshot.py`'s `season_order_week` is a verbatim alias of that raw week (the recorded alias
// landmine). The manifest hands a client the list of published kickoff DAYS precisely so a
// selector never has to ask about a week, and a day cannot collide with itself.

import { DAY_PICKER_LABEL } from "@/lib/ncaaf-copy"
import type { NcaafGameDayRef } from "@/lib/ncaaf"
import { cn } from "@/lib/utils"

/** A published day, in the reader's words.
 *
 * ⚠️ PARSED AS A LOCAL DATE, DELIBERATELY. `new Date("2026-08-29")` parses as UTC MIDNIGHT, which
 * renders as August 28th for every reader west of Greenwich — the day label would be off by one
 * for the entire US audience of a US sport. Splitting the parts and building a local date is what
 * keeps the label the same day the API named. */
export function formatGameDay(gameDay: string): string {
  const [y, m, d] = gameDay.split("-").map(Number)
  if (!y || !m || !d) return gameDay
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  })
}

export function NcaafDayPicker({
  days,
  selected,
  onSelect,
}: {
  days: NcaafGameDayRef[]
  selected: string | null
  onSelect: (gameDay: string) => void
}) {
  if (days.length === 0) return null
  return (
    <nav data-testid="ncaaf-day-picker" aria-label={DAY_PICKER_LABEL} className="space-y-1.5">
      <div className="text-[10px] uppercase tracking-widest text-gray-500">{DAY_PICKER_LABEL}</div>
      {/* Scrolls INSIDE its own container on a phone. A long season is many days and the page body
          must never scroll sideways (the NF-C4 lesson: a table that overflows its own box leaves
          the document tidy while the reader drags). */}
      <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
        {days.map((d) => {
          const active = d.game_day === selected
          return (
            <button
              key={d.game_day}
              type="button"
              data-testid="ncaaf-day-option"
              data-game-day={d.game_day}
              data-active={active ? "true" : "false"}
              aria-current={active ? "true" : undefined}
              onClick={() => onSelect(d.game_day)}
              className={cn(
                "shrink-0 rounded-lg border px-3 py-1.5 text-left transition-colors",
                active
                  ? "border-emerald-600/60 bg-emerald-950/40 text-white"
                  : "border-[#1e1e1e] bg-[#0d0d0d] text-gray-400 hover:border-[#2a2a2a] hover:text-gray-200",
              )}
            >
              <span className="block whitespace-nowrap text-xs font-medium">
                {formatGameDay(d.game_day)}
              </span>
              <span className="block whitespace-nowrap text-[10px] tabular-nums text-gray-500">
                {d.n_games} {d.n_games === 1 ? "game" : "games"}
              </span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}
