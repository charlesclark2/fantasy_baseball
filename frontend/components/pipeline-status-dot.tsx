"use client"

// A1.4 — live prediction-freshness indicator for the dashboard header.
// Fetches GET /pipeline/status and renders a green/yellow/red dot + a
// non-technical tooltip. Falls back to the red "updating" state on any error so
// the UI never overstates freshness. This is the live replacement for the
// mock <SignalFreshness /> block.

import { useEffect, useState } from "react"
import { Info } from "lucide-react"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"

type PipelineStatus = {
  indicator: "green" | "yellow" | "red"
  message: string
  predictions_ready: boolean
  lineup_confirmed: boolean
  last_updated_at: string | null
  n_games_scored: number
  n_qualified_bets: number
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

const DOT: Record<string, string> = {
  green: "bg-[#10b981]",
  yellow: "bg-[#f59e0b]",
  red: "bg-[#ef4444]",
}

// Non-technical tooltip copy (per A1.4 ACs) — understandable without knowing
// what "sub-model signals" are.
const TOOLTIP: Record<string, string> = {
  green: "Predictions based on confirmed lineups, updated above.",
  yellow:
    "Predictions based on projected lineups — they will update when lineups confirm.",
  red: "Pipeline running — check back in a few minutes.",
}

function formatLocal(ts: string | null): string | null {
  if (!ts) return null
  // Snowflake TIMESTAMP_NTZ comes back without a zone; treat it as UTC then
  // render in the BROWSER's local timezone (satisfies "local time, not UTC").
  const iso = ts.endsWith("Z") || /[+-]\d\d:?\d\d$/.test(ts) ? ts : ts + "Z"
  const d = new Date(iso)
  if (isNaN(d.getTime())) return null
  return d.toLocaleString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  })
}

export function PipelineStatusDot() {
  const [status, setStatus] = useState<PipelineStatus | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/pipeline/status`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!cancelled && d) setStatus(d as PipelineStatus)
      })
      .catch(() => {
        /* keep null → red "updating" default */
      })
    return () => {
      cancelled = true
    }
  }, [])

  const indicator = status?.indicator ?? "red"
  const tooltip = TOOLTIP[indicator]
  const updated = formatLocal(status?.last_updated_at ?? null)
  const lineupNote = status?.lineup_confirmed
    ? "Lineups confirmed"
    : "Projected lineups"

  return (
    <div className="flex items-center gap-2">
      <span
        className={`h-2 w-2 rounded-full ${DOT[indicator]} shrink-0`}
        aria-hidden
      />
      <span className="text-xs text-gray-500">
        {updated ? (
          <>
            Last updated: <span className="text-gray-400">{updated}</span>
            {" · "}
            {lineupNote}
          </>
        ) : (
          "Predictions updating…"
        )}
      </span>
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Info className="h-3 w-3 text-gray-600 cursor-default" />
          </TooltipTrigger>
          <TooltipContent side="right">
            <span className="text-xs">{tooltip}</span>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  )
}
