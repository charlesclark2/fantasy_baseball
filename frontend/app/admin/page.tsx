"use client"

import Link from "next/link"
import { ChevronDown, ChevronUp, CheckCircle, Lock, RefreshCw } from "lucide-react"
import { Nav } from "@/components/nav"
import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
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

interface MonthlyFinances {
  month: string
  month_label: string
  fixed_cost: number
  snowflake_cost: number | null
  aws_cost: number | null
  railway_cost: number | null
  dagster_cost: number | null
  total_cost: number
  betting_pl: number
  subscription_revenue: number
  net: number
}

interface FinancesData {
  months: MonthlyFinances[]
  fixed_breakdown: Record<string, number>
  notes: string[]
}

interface FinancesConfig {
  railway_monthly_estimate: number
  dagster_monthly_estimate: number
}

interface DataQualityReport {
  report_id: string
  user_email: string
  page_url: string
  description: string
  created_at: string
  game_pk?: number
  resolved_at?: string
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

function fmt(val: number | null, prefix = "$"): string {
  if (val === null) return "—"
  return `${prefix}${Math.abs(val).toFixed(2)}`
}

function PLCell({ value }: { value: number }) {
  const color = value > 0 ? "#10b981" : value < 0 ? "#ef4444" : "#6b7280"
  const sign = value > 0 ? "+" : ""
  return <span style={{ color }}>{sign}${value.toFixed(2)}</span>
}

export default function AdminPage() {
  const { accessToken, email, isAdmin } = useAuth()
  const qc = useQueryClient()
  const [refreshState, setRefreshState] = useState<"idle" | "loading" | "done" | "error">("idle")
  const [showFixedBreakdown, setShowFixedBreakdown] = useState(false)
  const [showResolved, setShowResolved] = useState(false)
  const [configDraft, setConfigDraft] = useState<FinancesConfig | null>(null)
  const [configSaving, setConfigSaving] = useState(false)

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

  const { data: finances, isLoading: financesLoading } = useQuery<FinancesData>({
    queryKey: ["admin-finances", accessToken],
    queryFn: () => apiFetch("/admin/finances", {}, accessToken),
    staleTime: 3_600_000,
    enabled: !!accessToken && isAdmin,
  })

  const { data: financesConfig } = useQuery<FinancesConfig>({
    queryKey: ["admin-finances-config", accessToken],
    queryFn: () => apiFetch("/admin/finances-config", {}, accessToken),
    staleTime: Infinity,
    enabled: !!accessToken && isAdmin,
  })

  const { data: dataQualityReports, isLoading: reportsLoading } = useQuery<DataQualityReport[]>({
    queryKey: ["admin-data-quality-reports", accessToken],
    queryFn: () => apiFetch("/admin/data-quality-reports", {}, accessToken),
    staleTime: 60_000,
    enabled: !!accessToken && isAdmin,
  })

  const resolveMutation = useMutation({
    mutationFn: (reportId: string) =>
      apiFetch(`/admin/data-quality-reports/${reportId}/resolve`, { method: "PATCH" }, accessToken),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-data-quality-reports"] }),
  })

  // Sync config into draft once loaded (only if draft not yet set)
  if (financesConfig && configDraft === null) {
    setConfigDraft(financesConfig)
  }

  async function saveFinancesConfig() {
    if (!configDraft) return
    setConfigSaving(true)
    try {
      await apiFetch("/admin/finances-config", { method: "PATCH", body: JSON.stringify(configDraft) }, accessToken)
      qc.invalidateQueries({ queryKey: ["admin-finances", accessToken] })
      qc.invalidateQueries({ queryKey: ["admin-finances-config", accessToken] })
    } finally {
      setConfigSaving(false)
    }
  }

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
            ? new Date(pipelineStatus.last_updated_at.endsWith("Z") ? pipelineStatus.last_updated_at : pipelineStatus.last_updated_at + "Z").toLocaleString("en-US", {
                month: "short",
                day: "numeric",
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
        {/* Monthly P&L */}
        <section className="rounded-lg border border-[#262626] bg-[#141414] p-6">
          <div className="mb-5 flex items-center justify-between">
            <h2 className="text-base font-semibold text-white">Monthly P&amp;L</h2>
            <button
              onClick={() => setShowFixedBreakdown((v) => !v)}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 transition-colors"
            >
              Fixed breakdown
              {showFixedBreakdown ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            </button>
          </div>

          {/* Editable variable estimates */}
          <div className="mb-5 rounded-lg border border-[#1e1e1e] bg-[#0a0a0a] p-4">
            <p className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-gray-500">
              Variable Estimates
            </p>
            <div className="flex flex-wrap gap-4 items-end">
              <label className="flex flex-col gap-1">
                <span className="text-[11px] text-gray-500">Railway ($/mo)</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={configDraft?.railway_monthly_estimate ?? ""}
                  onChange={(e) => setConfigDraft((d) => d ? { ...d, railway_monthly_estimate: parseFloat(e.target.value) || 0 } : d)}
                  className="w-28 rounded border border-[#2a2a2a] bg-[#141414] px-2 py-1 text-sm text-white focus:border-blue-500 focus:outline-none"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[11px] text-gray-500">Dagster+ ($/mo)</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={configDraft?.dagster_monthly_estimate ?? ""}
                  onChange={(e) => setConfigDraft((d) => d ? { ...d, dagster_monthly_estimate: parseFloat(e.target.value) || 0 } : d)}
                  className="w-28 rounded border border-[#2a2a2a] bg-[#141414] px-2 py-1 text-sm text-white focus:border-blue-500 focus:outline-none"
                />
              </label>
              <Button
                size="sm"
                onClick={saveFinancesConfig}
                disabled={configSaving || configDraft === null}
                className="h-[30px] text-xs"
              >
                {configSaving ? "Saving…" : "Save"}
              </Button>
            </div>
            <p className="mt-2 text-[10px] text-gray-600">
              Dagster+ default: $50/mo. Railway: check your dashboard. Both persisted to S3.
            </p>
          </div>

          {showFixedBreakdown && finances?.fixed_breakdown && (
            <div className="mb-5 rounded-lg border border-[#1e1e1e] bg-[#0a0a0a] p-4">
              <p className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-gray-500">
                Fixed Monthly Costs
              </p>
              <ul className="space-y-1.5">
                {Object.entries(finances.fixed_breakdown).map(([name, cost]) => (
                  <li key={name} className="flex justify-between text-sm">
                    <span className="text-gray-400">{name}</span>
                    <span className="text-white">${cost.toFixed(2)}</span>
                  </li>
                ))}
                <li className="flex justify-between border-t border-[#262626] pt-2 text-sm font-medium">
                  <span className="text-gray-300">Total Fixed</span>
                  <span className="text-white">
                    ${Object.values(finances.fixed_breakdown).reduce((a, b) => a + b, 0).toFixed(2)}/mo
                  </span>
                </li>
              </ul>
            </div>
          )}

          {financesLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-8 rounded bg-[#1a1a1a] animate-pulse" />
              ))}
            </div>
          ) : !finances?.months.length ? (
            <p className="text-sm text-gray-500">No data available.</p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[#262626]">
                      {["Month", "Fixed", "Snowflake", "AWS", "Railway", "Dagster", "Total Cost", "Betting P&L", "Subs", "Net"].map((h) => (
                        <th key={h} className="pb-3 pr-4 text-left text-xs font-semibold uppercase tracking-widest text-gray-500 last:pr-0 whitespace-nowrap">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1a1a1a]">
                    {finances.months.map((m) => (
                      <tr key={m.month} className="hover:bg-[#1a1a1a]">
                        <td className="py-3 pr-4 text-xs font-medium text-white whitespace-nowrap">{m.month_label}</td>
                        <td className="py-3 pr-4 text-xs text-gray-400 whitespace-nowrap">${m.fixed_cost.toFixed(2)}</td>
                        <td className="py-3 pr-4 text-xs text-gray-400 whitespace-nowrap">{fmt(m.snowflake_cost)}</td>
                        <td className="py-3 pr-4 text-xs text-gray-400 whitespace-nowrap">{fmt(m.aws_cost)}</td>
                        <td className="py-3 pr-4 text-xs text-gray-400 whitespace-nowrap">{fmt(m.railway_cost)}</td>
                        <td className="py-3 pr-4 text-xs text-gray-400 whitespace-nowrap">{fmt(m.dagster_cost)}</td>
                        <td className="py-3 pr-4 text-xs font-medium text-white whitespace-nowrap">${m.total_cost.toFixed(2)}</td>
                        <td className="py-3 pr-4 text-xs whitespace-nowrap">
                          <PLCell value={m.betting_pl} />
                        </td>
                        <td className="py-3 pr-4 text-xs text-gray-400 whitespace-nowrap">${m.subscription_revenue.toFixed(2)}</td>
                        <td className="py-3 text-xs font-semibold whitespace-nowrap">
                          <PLCell value={m.net} />
                        </td>
                      </tr>
                    ))}
                    {/* Annual totals row */}
                    {(() => {
                      const totals = finances.months.reduce(
                        (acc, m) => ({
                          fixed: acc.fixed + m.fixed_cost,
                          total_cost: acc.total_cost + m.total_cost,
                          betting_pl: acc.betting_pl + m.betting_pl,
                          subs: acc.subs + m.subscription_revenue,
                          net: acc.net + m.net,
                        }),
                        { fixed: 0, total_cost: 0, betting_pl: 0, subs: 0, net: 0 }
                      )
                      return (
                        <tr className="border-t-2 border-[#333] bg-[#0f0f0f]">
                          <td className="py-3 pr-4 text-xs font-bold text-gray-300 whitespace-nowrap uppercase tracking-widest">YTD Total</td>
                          <td className="py-3 pr-4 text-xs font-medium text-gray-300 whitespace-nowrap">${totals.fixed.toFixed(2)}</td>
                          <td className="py-3 pr-4 text-xs text-gray-500 whitespace-nowrap">—</td>
                          <td className="py-3 pr-4 text-xs text-gray-500 whitespace-nowrap">—</td>
                          <td className="py-3 pr-4 text-xs text-gray-500 whitespace-nowrap">—</td>
                          <td className="py-3 pr-4 text-xs text-gray-500 whitespace-nowrap">—</td>
                          <td className="py-3 pr-4 text-xs font-bold text-white whitespace-nowrap">${totals.total_cost.toFixed(2)}</td>
                          <td className="py-3 pr-4 text-xs font-bold whitespace-nowrap">
                            <PLCell value={totals.betting_pl} />
                          </td>
                          <td className="py-3 pr-4 text-xs font-medium text-gray-300 whitespace-nowrap">${totals.subs.toFixed(2)}</td>
                          <td className="py-3 text-xs font-bold whitespace-nowrap">
                            <PLCell value={totals.net} />
                          </td>
                        </tr>
                      )
                    })()}
                  </tbody>
                </table>
              </div>
              {finances.notes.length > 0 && (
                <ul className="mt-4 space-y-1">
                  {finances.notes.map((note, i) => (
                    <li key={i} className="text-[11px] text-gray-600">⚠ {note}</li>
                  ))}
                </ul>
              )}
            </>
          )}
        </section>

        {/* Data Quality Reports */}
        <section className="rounded-lg border border-[#262626] bg-[#141414] p-6">
          <div className="mb-5 flex items-center justify-between">
            <h2 className="text-base font-semibold text-white">Data Quality Reports</h2>
            <button
              onClick={() => setShowResolved((v) => !v)}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 transition-colors"
            >
              {showResolved ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              {showResolved ? "Hide resolved" : "Show resolved"}
            </button>
          </div>
          {reportsLoading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-10 rounded bg-[#1a1a1a] animate-pulse" />
              ))}
            </div>
          ) : !dataQualityReports || dataQualityReports.length === 0 ? (
            <p className="text-sm text-gray-500">No reports submitted yet.</p>
          ) : (() => {
            const visible = dataQualityReports.filter((r) => showResolved || !r.resolved_at)
            if (visible.length === 0) {
              return <p className="text-sm text-gray-500">All reports resolved. <button onClick={() => setShowResolved(true)} className="underline hover:text-gray-300">Show resolved</button></p>
            }
            return (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[#262626] text-left text-[11px] font-semibold uppercase tracking-widest text-gray-500">
                      <th className="pb-3 pr-4">Submitted</th>
                      <th className="pb-3 pr-4">User</th>
                      <th className="pb-3 pr-4">Page</th>
                      <th className="pb-3 pr-4">Description</th>
                      <th className="pb-3" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1e1e1e]">
                    {visible.map((r) => (
                      <tr key={r.report_id} className={r.resolved_at ? "opacity-40" : "text-gray-300"}>
                        <td className="py-3 pr-4 whitespace-nowrap text-xs text-gray-500">
                          {new Date(r.created_at).toLocaleString("en-US", {
                            month: "short", day: "numeric", hour: "numeric",
                            minute: "2-digit", timeZoneName: "short",
                          })}
                        </td>
                        <td className="py-3 pr-4 text-xs whitespace-nowrap">{r.user_email}</td>
                        <td className="py-3 pr-4 text-xs text-gray-500 max-w-[200px] truncate">
                          {r.page_url.replace(/^https?:\/\/[^/]+/, "")}
                          {r.game_pk ? <span className="ml-1 text-gray-600">(#{r.game_pk})</span> : null}
                        </td>
                        <td className="py-3 pr-4 text-xs text-gray-400 max-w-[300px]">{r.description}</td>
                        <td className="py-3 whitespace-nowrap">
                          {r.resolved_at ? (
                            <span className="flex items-center gap-1 text-xs text-[#10b981]">
                              <CheckCircle className="h-3.5 w-3.5" /> Resolved
                            </span>
                          ) : (
                            <button
                              onClick={() => resolveMutation.mutate(r.report_id)}
                              disabled={resolveMutation.isPending}
                              className="flex items-center gap-1 rounded border border-[#2a2a2a] px-2 py-1 text-xs text-gray-400 hover:border-[#10b981] hover:text-[#10b981] transition-colors disabled:opacity-50"
                            >
                              <CheckCircle className="h-3 w-3" /> Resolve
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          })()}
        </section>

      </main>
    </div>
    </AdminGuard>
  )
}
