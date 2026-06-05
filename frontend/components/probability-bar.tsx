import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

/**
 * ProbabilityBar
 *
 * Renders a horizontal credible-interval bar that zooms in on the
 * relevant probability range for readability (rather than 0–100%).
 *
 * @param ciLow              - Lower bound of the 80% credible interval, e.g. 0.48
 * @param ciHigh             - Upper bound of the 80% credible interval, e.g. 0.61
 * @param modelProb          - Model point estimate, e.g. 0.583
 * @param marketProb         - Bookmaker implied probability, e.g. 0.541
 * @param showLabels         - Whether to render percentage labels below the bar (default: true)
 * @param showHighConviction - Whether to show the HIGH CONVICTION badge when the
 *                             full CI is above marketProb (default: true)
 * @param className          - Optional Tailwind class overrides for the outermost container
 */

export interface ProbabilityBarProps {
  ciLow: number
  ciHigh: number
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
  // ---------------------------------------------------------------------------
  // Derived values
  // ---------------------------------------------------------------------------

  const isHighConviction = ciLow > marketProb

  // Build a readable display window with 8-point padding on each side,
  // clamped to [0, 1], rounded to the nearest 5% for clean axis endpoints.
  const allValues = [ciLow, ciHigh, modelProb, marketProb]
  const minVal = Math.min(...allValues)
  const maxVal = Math.max(...allValues)
  const padding = 0.08
  const rangeMin = Math.max(0, Math.floor((minVal - padding) * 20) / 20)
  const rangeMax = Math.min(1, Math.ceil((maxVal + padding) * 20) / 20)
  const range = rangeMax - rangeMin

  /** Convert an absolute probability to a % position within the display window */
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

      {/* Above-bar labels: "Model" and "Market" */}
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

      {/* Bar track */}
      <div className="relative h-3 w-full rounded-full bg-[#262626]">
        {/* CI fill — solid emerald */}
        <div
          className="absolute top-0 h-full rounded-full bg-[#10b981]"
          style={{
            left: toPos(ciLow),
            width: `${((ciHigh - ciLow) / range) * 100}%`,
          }}
        />

        {/* Model tick — white vertical line */}
        <div
          className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-0.5 h-5 rounded-full bg-white shadow shadow-white/30"
          style={{ left: toPos(modelProb) }}
        />

        {/* Market tick — gray vertical line */}
        <div
          className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-0.5 h-5 rounded-full bg-gray-400"
          style={{ left: toPos(marketProb) }}
        />
      </div>

      {/* Below-bar percentage labels */}
      {showLabels && (
        <div className="relative h-5 mt-1 text-[10px]">
          {/* ciLow */}
          <span
            className="absolute -translate-x-1/2 text-[#10b981]/80"
            style={{ left: toPos(ciLow) }}
          >
            {fmt(ciLow)}
          </span>

          {/* marketProb */}
          <span
            className="absolute -translate-x-1/2 text-gray-500"
            style={{ left: toPos(marketProb) }}
          >
            {fmt(marketProb)}
          </span>

          {/* modelProb */}
          <span
            className="absolute -translate-x-1/2 text-white font-medium"
            style={{ left: toPos(modelProb) }}
          >
            {fmt(modelProb)}
          </span>

          {/* ciHigh */}
          <span
            className="absolute -translate-x-1/2 text-[#10b981]/80"
            style={{ left: toPos(ciHigh) }}
          >
            {fmt(ciHigh)}
          </span>
        </div>
      )}

      {/* Axis endpoints */}
      <div className="mt-2 flex justify-between text-[9px] text-gray-600">
        <span>{fmt(rangeMin)}</span>
        <span>{fmt(rangeMax)}</span>
      </div>
    </div>
  )
}

export default ProbabilityBar
