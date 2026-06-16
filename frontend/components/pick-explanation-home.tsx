"use client"

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
  topDrivers,
  servedTier,
}: {
  narrative?: string | null
  topDrivers?: PickDriver[] | null
  servedTier?: string | null
}) {
  const hasContent = narrative || (topDrivers && topDrivers.length > 0)
  if (!hasContent) return null
  return (
    <div className="mt-4 rounded-lg border border-[#1e1e1e] bg-[#0d0d0d] px-4 py-3">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-widest">
          Model reasoning
        </span>
        <ServedTierBadge tier={servedTier} />
      </div>
      {narrative && (
        <p className="text-xs leading-relaxed text-gray-400">{narrative}</p>
      )}
      {topDrivers && topDrivers.length > 0 && (
        <MiniDriverList drivers={topDrivers} />
      )}
    </div>
  )
}
