"use client"

import { cn } from "@/lib/utils"

interface CompactProbabilityBarProps {
  ciLow: number
  ciHigh: number
  modelProb: number
  marketProb: number
  className?: string
}

export function CompactProbabilityBar({
  ciLow,
  ciHigh,
  modelProb,
  marketProb,
  className,
}: CompactProbabilityBarProps) {
  // Fixed scale from 35% to 75% for consistent comparison across rows
  const rangeMin = 0.35
  const rangeMax = 0.75
  const range = rangeMax - rangeMin

  // Convert probability to percentage position within the fixed display range
  const toPosition = (prob: number) => Math.max(0, Math.min(100, ((prob - rangeMin) / range) * 100))
  
  // Check if entire CI is to the right of market probability (high conviction)
  const isHighConviction = ciLow > marketProb

  const ciLowPos = toPosition(ciLow)
  const ciHighPos = toPosition(ciHigh)
  const modelPos = toPosition(modelProb)
  const marketPos = toPosition(marketProb)

  // Format as percentage
  const formatPct = (val: number) => `${(val * 100).toFixed(0)}%`

  return (
    <div className={cn("w-[140px]", className)}>
      {/* Bar Container - increased height for taller model marker */}
      <div className="relative h-5">
        {/* Background Track - 8px height, centered */}
        <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-2 bg-muted-foreground/20 rounded-full" />

        {/* CI Range Fill - 8px height, centered */}
        <div
          className="absolute top-1/2 -translate-y-1/2 h-2 bg-emerald-500/50 rounded-full"
          style={{
            left: `${ciLowPos}%`,
            width: `${ciHighPos - ciLowPos}%`,
          }}
        />

        {/* Market Probability Diamond (orange) - positioned above the bar */}
        <div
          className="absolute text-amber-500 text-[10px] leading-none"
          style={{ 
            left: `${marketPos}%`, 
            transform: 'translateX(-50%)',
            top: '0px'
          }}
        >
          ◆
        </div>

        {/* Model Probability Line (white vertical indicator) - 16px tall */}
        <div
          className="absolute w-0.5 h-4 bg-white rounded-full"
          style={{ 
            left: `${modelPos}%`, 
            top: '50%',
            transform: 'translateX(-50%) translateY(-50%)'
          }}
        />
      </div>

      {/* Labels Below */}
      <div className="flex justify-between mt-1 text-[9px] text-muted-foreground font-mono">
        <span className="text-emerald-400/70">{formatPct(ciLow)}</span>
        <span className="text-white/90 font-medium">{formatPct(modelProb)}</span>
        <span className="text-emerald-400/70">{formatPct(ciHigh)}</span>
      </div>

      {/* High Conviction Badge - shown when entire CI is to the right of market */}
      {isHighConviction && (
        <div className="mt-1">
          <span className="text-[9px] font-medium text-emerald-400 bg-emerald-500/20 px-1.5 py-0.5 rounded">
            High Conviction
          </span>
        </div>
      )}
    </div>
  )
}
