"use client"

import { useState } from "react"
import dynamic from "next/dynamic"
import type { PickDriver } from "@/components/pick-explanation"

export type { PickDriver }

const MiniDriverList = dynamic(
  () => import("@/components/pick-explanation").then((m) => ({ default: m.MiniDriverList })),
  { ssr: false, loading: () => null },
)
const ServedTierBadge = dynamic(
  () => import("@/components/pick-explanation").then((m) => ({ default: m.ServedTierBadge })),
  { ssr: false, loading: () => null },
)

export function FeaturedPickExplanation({
  narrative,
  topDriversH2h,
  topDriversTotals,
  defaultMarket,
  servedTier,
}: {
  narrative?: string | null
  topDriversH2h?: PickDriver[] | null
  topDriversTotals?: PickDriver[] | null
  defaultMarket?: string | null
  servedTier?: string | null
}) {
  const [activeMarket, setActiveMarket] = useState<"h2h" | "totals">(
    defaultMarket === "totals" ? "totals" : "h2h"
  )

  const hasH2h = topDriversH2h && topDriversH2h.length > 0
  const hasTotals = topDriversTotals && topDriversTotals.length > 0
  const showToggle = hasH2h && hasTotals
  const activeDrivers = activeMarket === "totals" ? topDriversTotals : topDriversH2h

  const hasContent = narrative || hasH2h || hasTotals
  if (!hasContent) return null

  return (
    <div className="mt-4 rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-4 py-3">
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-widest">
            Model reasoning
          </span>
          {showToggle && (
            <div className="flex gap-1">
              <button
                onClick={() => setActiveMarket("h2h")}
                className={`px-2 py-0.5 text-xs rounded font-medium transition-colors ${
                  activeMarket === "h2h"
                    ? "bg-[#10b981] text-black"
                    : "bg-[#1e1e1e] text-gray-400 hover:text-gray-200"
                }`}
              >
                H2H
              </button>
              <button
                onClick={() => setActiveMarket("totals")}
                className={`px-2 py-0.5 text-xs rounded font-medium transition-colors ${
                  activeMarket === "totals"
                    ? "bg-[#10b981] text-black"
                    : "bg-[#1e1e1e] text-gray-400 hover:text-gray-200"
                }`}
              >
                Totals
              </button>
            </div>
          )}
        </div>
        <ServedTierBadge tier={servedTier} />
      </div>
      {narrative && (
        <p className="text-xs leading-relaxed text-gray-400">{narrative}</p>
      )}
      {activeDrivers && activeDrivers.length > 0 && (
        <MiniDriverList drivers={activeDrivers} />
      )}
    </div>
  )
}
