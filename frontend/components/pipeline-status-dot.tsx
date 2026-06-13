"use client"

// A1.4 — pick-freshness breakdown for the dashboard header.
// Counts picks by lineup_confirmed status and renders green/yellow/red dot counts.
// Green = confirmed lineup, Yellow = projected lineup, Red = no predictions.

type Pick = {
  lineup_confirmed: boolean | null
}

type Props = {
  picks: Pick[]
  isLoading?: boolean
}

export function PipelineStatusDot({ picks, isLoading }: Props) {
  if (isLoading) {
    return (
      <div className="flex items-center gap-3">
        <div className="h-3 w-32 animate-pulse rounded bg-[#262626]" />
      </div>
    )
  }

  if (picks.length === 0) {
    return (
      <div className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full bg-[#ef4444] shrink-0" />
        <span className="text-xs text-gray-500">No predictions for today</span>
      </div>
    )
  }

  const green = picks.filter((p) => p.lineup_confirmed === true).length
  const yellow = picks.filter((p) => !p.lineup_confirmed).length

  return (
    <div className="flex items-center gap-4">
      {green > 0 && (
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-[#10b981] shrink-0" />
          <span className="text-xs text-gray-400">
            <span className="font-semibold text-white">{green}</span>
            {" "}confirmed lineup{green !== 1 ? "s" : ""}
          </span>
        </div>
      )}
      {yellow > 0 && (
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-[#f59e0b] shrink-0" />
          <span className="text-xs text-gray-400">
            <span className="font-semibold text-white">{yellow}</span>
            {" "}projected lineup{yellow !== 1 ? "s" : ""}
          </span>
        </div>
      )}
    </div>
  )
}
