"use client"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

interface ProbabilityBarProps {
  ciLow: number
  ciHigh: number
  modelProb: number
  marketProb: number
  className?: string
}

export function ProbabilityBar({
  ciLow,
  ciHigh,
  modelProb,
  marketProb,
  className,
}: ProbabilityBarProps) {
  // Determine if high conviction (entire CI above market probability)
  const isHighConviction = ciLow > marketProb

  // Calculate display range for readability (add padding around the values)
  const allValues = [ciLow, ciHigh, modelProb, marketProb]
  const minVal = Math.min(...allValues)
  const maxVal = Math.max(...allValues)
  const padding = 0.08
  const rangeMin = Math.max(0, Math.floor((minVal - padding) * 10) / 10)
  const rangeMax = Math.min(1, Math.ceil((maxVal + padding) * 10) / 10)
  const range = rangeMax - rangeMin

  // Convert probability to percentage position within the display range
  const toPosition = (prob: number) => ((prob - rangeMin) / range) * 100

  const ciLowPos = toPosition(ciLow)
  const ciHighPos = toPosition(ciHigh)
  const modelPos = toPosition(modelProb)
  const marketPos = toPosition(marketProb)

  // Format as percentage
  const formatPct = (val: number) => `${(val * 100).toFixed(1)}%`

  return (
    <div className={cn("w-full", className)}>
      {/* High Conviction Badge */}
      {isHighConviction && (
        <div className="mb-2">
          <Badge
            variant="secondary"
            className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30 text-xs"
          >
            High Conviction
          </Badge>
        </div>
      )}

      {/* Bar Container */}
      <div className="relative h-8 w-full">
        {/* Background Track */}
        <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-2 bg-muted rounded-full" />

        {/* CI Range Fill */}
        <div
          className="absolute top-1/2 -translate-y-1/2 h-2 bg-emerald-500/40 rounded-full"
          style={{
            left: `${ciLowPos}%`,
            width: `${ciHighPos - ciLowPos}%`,
          }}
        />

        {/* Market Probability Tick (gray/amber line) */}
        <div
          className="absolute top-1/2 -translate-y-1/2 w-0.5 h-5 bg-amber-500 rounded-full"
          style={{ left: `${marketPos}%` }}
        >
          <div className="absolute -top-6 left-1/2 -translate-x-1/2 text-[10px] text-amber-400 whitespace-nowrap">
            Market
          </div>
        </div>

        {/* Model Probability Line (vertical indicator) */}
        <div
          className="absolute top-1/2 -translate-y-1/2 w-1 h-6 bg-emerald-400 rounded-full shadow-sm shadow-emerald-500/50"
          style={{ left: `${modelPos}%` }}
        />
      </div>

      {/* Labels Below */}
      <div className="relative h-5 mt-1 text-[10px] text-muted-foreground">
        {/* CI Low Label */}
        <div
          className="absolute -translate-x-1/2 text-emerald-400/80"
          style={{ left: `${ciLowPos}%` }}
        >
          {formatPct(ciLow)}
        </div>

        {/* Model Prob Label (center, slightly emphasized) */}
        <div
          className="absolute -translate-x-1/2 text-emerald-400 font-medium"
          style={{ left: `${modelPos}%` }}
        >
          {formatPct(modelProb)}
        </div>

        {/* CI High Label */}
        <div
          className="absolute -translate-x-1/2 text-emerald-400/80"
          style={{ left: `${ciHighPos}%` }}
        >
          {formatPct(ciHigh)}
        </div>

        {/* Market Prob Label */}
        <div
          className="absolute -translate-x-1/2 text-amber-400/80"
          style={{ left: `${marketPos}%` }}
        >
          {formatPct(marketProb)}
        </div>
      </div>

      {/* Range Scale */}
      <div className="flex justify-between mt-2 text-[9px] text-muted-foreground/50">
        <span>{formatPct(rangeMin)}</span>
        <span>{formatPct(rangeMax)}</span>
      </div>
    </div>
  )
}
