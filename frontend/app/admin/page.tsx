"use client"

import Link from "next/link"
import { Lock, RefreshCw } from "lucide-react"
import { Nav } from "@/components/nav"
import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { apiFetch } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { AdminGuard } from "@/components/auth-guard"
import { Button } from "@/components/ui/button"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PipelineStatus {
  run_date: string | null
  predictions_ready: boolean
  lineup_confirmed: boolean
  last_updated_at: string | null
  n_games_scored: number
  n_qualified_bets: number
  signal_completeness_score: number | null
  avg_feature_coverage_score: number | null
  pipeline_status: string
  indicator: string
  message: string
}

interface PipelineRun {
  run_id: string
  timestamp_et: string
  job_name: string
  duration_seconds: number | null
  status: "success" | "warning" | "failed" | "running"
  notes: string
}

interface ModelFreshness {
  model_name: string
  target: string
  version: string
  last_trained_date: string
  days_since_training: number
  status: "healthy" | "watch" | "stale"
}

interface SnowflakeCredits {
  month: string
  month_label: string
  compute_credits: number
  cloud_service_credits: number
  total_credits: number
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusColor(status: string): string {
  if (status === "healthy" || status === "success") return "#10b981"
  if (status === "watch" || status === "warning" || status === "running") return "#f59e0b"
  return "#ef4444"
}

function StatusDot({ status }: { status: string }) {
  return (
    <span
      className="inline-block h-2 w-2 rounded-full flex-shrink-0"
      style={{ backgroundColor: statusColor(status) }}
    />
  )
}

function RunBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    success: "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30",
    warning: "bg-amber-500/15 text-amber-400 border border-amber-500/30",
    running: "bg-amber-500/15 text-amber-400 border border-amber-500/30",
    failed: "bg-red-500/15 text-red-400 border border-red-500/30",
  }
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium uppercase tracking-wide ${styles[status] ?? styles.warning}`}
    >
      {status}
    </span>
  )
}

function fmtDuration(seconds: number | null): string {
  if (seconds === null) return "—"
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}m ${s}s`
}

function indicatorToStatus(indicator: string): string {
  if (indicator === "green") return "healthy"
  if (indicator === "yellow") return "watch"
  return "failed"
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdminPage() {
  const { accessToken, email, isAdmin } = useAuth()
  const qc = useQueryClient()
  const [refreshState, setRefreshState] = useState<"idle" | "loading" | "done" | "error">("idle")

  const { data: pipelineStatus, isLoading: statusLoading } = useQuery<PipelineStatus>({
    queryKey: ["pipeline-status", accessToken],
    queryFn: () => apiFetch("/pipeline/status", {}, accessToken),
    staleTime: 60_000,
    enabled: !!accessToken && isAdmin,
  })

  const { data: pipelineRuns, isLoading: runsLoading } = useQuery<PipelineRun[]>({
    queryKey: ["pipeline-runs", accessToken],
    queryFn: () => apiFetch("/admin/pipeline-runs", {}, accessToken),
    staleTime: 120_000,
    enabled: !!accessToken && isAdmin,
  })

  const { data: modelFreshness, isLoading: freshnessLoading } = useQuery<ModelFreshness[]>({
    queryKey: ["model-freshness", accessToken],
    queryFn: () => apiFetch("/admin/model-freshness", {}, accessToken),
    staleTime: 300_000,
    enabled: !!accessToken && isAdmin,
  })

  const { data: sfCredits, isLoading: creditsLoading } = useQuery<SnowflakeCredits[]>({
    queryKey: ["snowflake-credits", accessToken],
    queryFn: () => apiFetch("/admin/snowflake-credits", {}, accessToken),
    staleTime: 3_600_000,
    enabled: !!accessToken && isAdmin,
  })

  async function handleRefresh() {
    setRefreshState("loading")
    try {
      await apiFetch("/admin/cache/invalidate", { method: "POST" }, accessToken)
      qc.invalidateQueries()
      setRefreshState("done")
    } catch {
      setRefreshState("error")
    }
  }

  // Derive status cards from live pipeline status
  const scs = pipelineStatus?.signal_completeness_score
  const statusCards = pipelineStatus
    ? [
        {
          label: "Last Dagster Run",
          value: pipelineStatus.last_updated_at
            ? new Date(pipelineStatus.last_updated_at).toLocaleTimeString("en-US", {
                hour: "numeric",
                minute: "2-digit",
                timeZoneName: "short",
              })
            : "—",
          subtitle: pipelineStatus.pipeline_status === "complete" ? "Completed successfully" : pipelineStatus.pipeline_status,
          status: indicatorToStatus(pipelineStatus.indicator),
        },
        {
          label: "Predictions Generated",
          value: String(pipelineStatus.n_games_scored),
          subtitle: "games scored today",
          status: pipelineStatus.predictions_ready ? "healthy" : "watch",
        },
        {
          label: "Qualified Bets",
          value: String(pipelineStatus.n_qualified_bets),
          subtitle: "picks passing decision gate",
          status: pipelineStatus.n_qualified_bets > 0 ? "healthy" : "watch",
        },
        {
          label: "Stale Signals",
          value: (scs ?? 0) >= 0.8 ? "None" : "Check signals",
          subtitle: "Signal completeness check",
          status: (scs ?? 0) >= 0.8 ? "healthy" : "watch",
        },
        {
          label: "Signal Completeness",
          value: scs != null ? scs.toFixed(2) : "—",
          subtitle: "Score above 0.80 threshold",
          status: scs == null ? "watch" : scs >= 0.8 ? "healthy" : scs >= 0.6 ? "watch" : "failed",
        },
      ]
    : []

  return (
    <AdminGuard>
    <div className="min-h-screen bg-[#0a0a0a] font-sans">
      <Nav authenticated activeLink="admin" userEmail={email} />

      <main className="mx-auto max-w-6xl px-4 py-8 space-y-8">
        {/* Page header */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">System Health</h1>
            <p className="mt-1 flex items-center gap-1.5 text-sm text-gray-500">
              <Lock className="h-3.5 w-3.5 text-red-500 flex-shrink-0" />
              Pipeline status and model freshness — admin only
            </p>
          </div>
          <span className="text-sm text-gray-500 pt-1">
            {pipelineStatus?.run_date ?? new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
          </span>
        </div>

        {/* Status cards + force refresh */}
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-widest text-gray-500">
              Status Overview
            </h2>
            <div className="flex items-center gap-3">
              {refreshState === "done" && (
                <span className="text-sm text-[#10b981]">
                  Cache cleared — next page load will re-query Snowflake
                </span>
              )}
              {refreshState === "error" && (
                <span className="text-sm text-[#ef4444]">
                  Cache invalidation failed — check API logs
                </span>
              )}
              <Button
                variant="ghost"
                size="sm"
                className="border border-[#262626] text-gray-400 hover:text-white hover:bg-[#141414]"
                onClick={handleRefresh}
                disabled={refreshState === "loading"}
              >
                <RefreshCw
                  className={`mr-1.5 h-3.5 w-3.5 ${refreshState === "loading" ? "animate-spin" : ""}`}
                />
                {refreshState === "loading" ? "Refreshing..." : "Force Refresh Predictions"}
              </Button>
            </div>
          </div>

          {statusLoading ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-24 rounded-lg bg-[#141414] border border-[#262626] animate-pulse" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {statusCards.map((card) => (
                <div
                  key={card.label}
                  className="rounded-lg bg-[#141414] p-5"
                  style={{
                    border: "1px solid #262626",
                    borderLeftWidth: "2px",
                    borderLeftColor: statusColor(card.status),
                  }}
                >
                  <div className="mb-3 flex items-center gap-2">
                    <StatusDot status={card.status} />
                    <span className="text-xs font-semibold uppercase tracking-widest text-gray-500">
                      {card.label}
                    </span>
                  </div>
                  <p className="text-2xl font-bold text-white">{card.value}</p>
                  <p className="mt-1 text-xs text-gray-500">{card.subtitle}</p>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Pipeline run log */}
        <section className="rounded-lg border border-[#262626] bg-[#141414] p-6">
          <h2 className="mb-5 text-base font-semibold text-white">Recent Pipeline Runs</h2>
          {runsLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-8 rounded bg-[#1a1a1a] animate-pulse" />
              ))}
            </div>
          ) : !pipelineRuns?.length ? (
            <p className="text-sm text-gray-500">No recent runs found.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#262626]">
                    {["Timestamp", "Job", "Duration", "Status", "Notes"].map((h) => (
                      <th
                        key={h}
                        className="pb-3 text-left text-xs font-semibold uppercase tracking-widest text-gray-500"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1a1a1a]">
                  {pipelineRuns.map((run, i) => (
                    <tr
                      key={`${run.run_id}-${i}`}
                      className={run.status === "failed" ? "bg-red-500/5" : "hover:bg-[#1a1a1a]"}
                    >
                      <td className="py-3 pr-4 font-mono text-xs text-gray-400 whitespace-nowrap">
                        {run.timestamp_et}
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs text-gray-300 whitespace-nowrap">
                        {run.job_name}
                      </td>
                      <td className="py-3 pr-4 text-xs text-gray-400 whitespace-nowrap">
                        {fmtDuration(run.duration_seconds)}
                      </td>
                      <td className="py-3 pr-4 whitespace-nowrap">
                        <RunBadge status={run.status} />
                      </td>
                      <td className="py-3 text-xs text-gray-500 max-w-xs">
                        {run.notes || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Model freshness + Snowflake credits note */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <section className="rounded-lg border border-[#262626] bg-[#141414] p-6">
            <h2 className="mb-5 text-base font-semibold text-white">Model Artifact Freshness</h2>
            {freshnessLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="h-8 rounded bg-[#1a1a1a] animate-pulse" />
                ))}
              </div>
            ) : !modelFreshness?.length ? (
              <p className="text-sm text-gray-500">No champion models in registry.</p>
            ) : (
              <ul className="space-y-3">
                {modelFreshness.map((m, i) => (
                  <li
                    key={`${m.target}-${m.version}-${i}`}
                    className="flex items-center justify-between gap-4 py-2 border-b border-[#1e1e1e] last:border-0"
                  >
                    <div className="flex-1 min-w-0">
                      <span className="block text-sm text-white font-medium truncate">
                        {m.model_name} ({m.version})
                      </span>
                      <span className="block text-xs text-gray-500">{m.target}</span>
                    </div>
                    <span
                      className="text-xs text-gray-500 whitespace-nowrap"
                      style={{ color: m.status === "watch" ? "#f59e0b" : m.status === "stale" ? "#ef4444" : "#6b7280" }}
                    >
                      {m.days_since_training}d ago
                    </span>
                    <StatusDot status={m.status} />
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="rounded-lg border border-[#262626] bg-[#141414] p-6">
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-base font-semibold text-white">Snowflake Credit Usage</h2>
              <Link
                href="https://app.snowflake.com"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-gray-500 hover:text-[#10b981] transition-colors"
              >
                Open console →
              </Link>
            </div>
            {creditsLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="h-8 rounded bg-[#1a1a1a] animate-pulse" />
                ))}
              </div>
            ) : !sfCredits?.length ? (
              <p className="text-sm text-gray-500">
                No credit data — role may need{" "}
                <code className="text-xs text-gray-400">IMPORTED PRIVILEGES</code> on the SNOWFLAKE database.
              </p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#262626]">
                    {["Month", "Compute cr.", "Cloud Svc cr.", "Total cr.", "Est. Cost"].map((h) => (
                      <th key={h} className="pb-3 text-left text-xs font-semibold uppercase tracking-widest text-gray-500">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1a1a1a]">
                  {sfCredits.map((row) => (
                    <tr key={row.month} className="hover:bg-[#1a1a1a]">
                      <td className="py-3 pr-4 text-xs font-medium text-white whitespace-nowrap">{row.month_label}</td>
                      <td className="py-3 pr-4 text-xs text-gray-400 whitespace-nowrap">{row.compute_credits.toFixed(1)}</td>
                      <td className="py-3 pr-4 text-xs text-gray-400 whitespace-nowrap">{row.cloud_service_credits.toFixed(1)}</td>
                      <td className="py-3 pr-4 text-xs text-gray-400 whitespace-nowrap">{row.total_credits.toFixed(1)}</td>
                      <td className="py-3 text-xs font-semibold text-[#10b981] whitespace-nowrap">
                        ${(row.total_credits * 2).toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </div>
      </main>
    </div>
    </AdminGuard>
  )
}
