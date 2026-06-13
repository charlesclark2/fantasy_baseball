import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

export interface ProbabilityBarProps {
  ciLow?: number | null
  ciHigh?: number | null
  modelProb: number
  marketProb: number
  showLabels?: boolean
  showHighConviction?: boolean
  className?: string
}

export function ProbabilityBar({
  ciLow,
  ciHigh,
  modelProb,
  marketProb,
  showLabels = true,
  showHighConviction = true,
  className,
}: ProbabilityBarProps) {
  const hasCi = ciLow != null && ciHigh != null

  const isHighConviction = hasCi && ciLow > marketProb

  // Build the display window only from values that are actually present.
  const allValues = hasCi ? [ciLow, ciHigh, modelProb, marketProb] : [modelProb, marketProb]
  const minVal = Math.min(...allValues)
  const maxVal = Math.max(...allValues)
  const padding = 0.08
  const rangeMin = Math.max(0, Math.floor((minVal - padding) * 20) / 20)
  const rangeMax = Math.min(1, Math.ceil((maxVal + padding) * 20) / 20)
  const range = rangeMax - rangeMin

  const toPos = (prob: number) => `${((prob - rangeMin) / range) * 100}%`
  const fmt = (val: number) => `${(val * 100).toFixed(1)}%`

  return (
    <div className={cn("w-full select-none", className)}>
      {/* HIGH CONVICTION badge */}
      {showHighConviction && isHighConviction && (
        <div className="mb-3">
          <Badge className="bg-[#10b981]/15 text-[#10b981] border border-[#10b981]/30 text-xs font-bold uppercase tracking-widest">
            High Conviction
          </Badge>
        </div>
      )}

      {/* Above-bar labels */}
      {showLabels && (
        <div className="relative h-5 mb-1 text-[10px]">
          <span
            className="absolute -translate-x-1/2 text-white font-semibold"
            style={{ left: toPos(modelProb) }}
          >
            Model
          </span>
          <span
            className="absolute -translate-x-1/2 text-gray-500"
            style={{ left: toPos(marketProb) }}
          >
            Market
          </span>
        </div>
      )}

      {/* Bar track */}
      <div className="relative h-3 w-full rounded-full bg-[#262626]">
        {/* CI fill — only when CI data is available */}
        {hasCi && (
          <div
            className="absolute top-0 h-full rounded-full bg-[#10b981]"
            style={{
              left: toPos(ciLow),
              width: `${((ciHigh - ciLow) / range) * 100}%`,
            }}
          />
        )}

        {/* Model tick — white */}
        <div
          className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-0.5 h-5 rounded-full bg-white shadow shadow-white/30"
          style={{ left: toPos(modelProb) }}
        />

        {/* Market tick — gray */}
        <div
          className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-0.5 h-5 rounded-full bg-gray-400"
          style={{ left: toPos(marketProb) }}
        />
      </div>

      {/* Below-bar percentage labels */}
      {showLabels && (
        <div className="relative h-5 mt-1 text-[10px]">
          {hasCi && (
            <>
              <span
                className="absolute -translate-x-1/2 text-[#10b981]/80"
                style={{ left: toPos(ciLow) }}
              >
                {fmt(ciLow)}
              </span>
              <span
                className="absolute -translate-x-1/2 text-[#10b981]/80"
                style={{ left: toPos(ciHigh) }}
              >
                {fmt(ciHigh)}
              </span>
            </>
          )}
          <span
            className="absolute -translate-x-1/2 text-gray-500"
            style={{ left: toPos(marketProb) }}
          >
            {fmt(marketProb)}
          </span>
          <span
            className="absolute -translate-x-1/2 text-white font-medium"
            style={{ left: toPos(modelProb) }}
          >
            {fmt(modelProb)}
          </span>
        </div>
      )}

      {/* Axis endpoints */}
      {showLabels && (
        <div className="mt-2 flex justify-between text-[9px] text-gray-600">
          <span>{fmt(rangeMin)}</span>
          <span>{fmt(rangeMax)}</span>
        </div>
      )}
    </div>
  )
}

export default ProbabilityBar
