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
  registry_version: string
  ledger_behind: boolean
  last_trained_date: string
  days_since_training: number
  status: "healthy" | "watch" | "stale"
}

interface SnowflakeCredits {
  month: string
  month_label: string
  compute_credits: number
  cloud_service_credits: number
  billed_credits: number
}

interface MonthlyFinances {
  month: string
  month_label: string
  fixed_cost: number
  snowflake_cost: number | null
  aws_cost: number | null
  ses_cost: number | null
  // E9.62 — optional on purpose. `frontend/` auto-deploys on merge but the API Lambda ships
  // only via infrastructure/lambda/deploy.sh, so this page goes live BEFORE the field exists
  // in the response. Undefined must render as "—", never as "$undefined" or a crash.
  vercel_cost?: number
  total_cost: number
  betting_pl: number
  subscription_revenue: number
  net: number
}

interface FinancesData {
  months: MonthlyFinances[]
  fixed_breakdown: Record<string, number>
  // E9.62 — per-month fixed costs. Optional for the same deploy-skew reason; the panel falls
  // back to the flat `fixed_breakdown` an older backend still sends.
  fixed_breakdown_by_month?: Record<string, Record<string, number>>
  aws_breakdown: Record<string, number>
  notes: string[]
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

interface CapturedTermStat {
  platform: string
  key: string
  occurrences: number
  avg_abs_weight: number
  score: number
  last_seen_at: string | null
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
  const [showAwsBreakdown, setShowAwsBreakdown] = useState(false)
  const [showResolved, setShowResolved] = useState(false)

  const { data: pipelineStatus, isLoading: statusLoading } = useQuery<PipelineStatus>({
    queryKey: ["pipeline-status", accessToken],
    queryFn: () => apiFetch("/pipeline/status?fallback_latest=true", {}, accessToken),
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

  // E11.24 — staleTime is 12h, NOT 1h, and that is a COST fix, not a perf tweak.
  // Both of these endpoints query ACCOUNT_USAGE.METERING_DAILY_HISTORY, and with a 1h staleTime an
  // admin tab left OPEN refetched both on every focus/interval — measured as 2 provisioning waits
  // per hour, around the clock (7/27: hours 01–09 unbroken), i.e. 42 of 793 COMPUTE_WH wakes in 8
  // days = 5.3%, purely from the page that DISPLAYS the bill. Two reasons 12h is not merely safer:
  //   1. this data is MONTH-grained (SnowflakeCredits / MonthlyFinances) — an hourly refetch cannot
  //      surface anything a 12-hourly one misses; and
  //   2. `account_usage` metering latency on this account is ~12h+ (E11.20-COST lesson-1), so an
  //      hourly refetch is GUARANTEED to return byte-identical numbers.
  // The companion server-side fix routes both queries to MONITOR_WH so they can never wake the
  // warehouse they are measuring — keep BOTH: the routing stops the wake, this stops the useless poll.
  const SF_COST_STALE_MS = 43_200_000 // 12h — see note above; do not lower without re-measuring wakes

  const { data: sfCredits, isLoading: creditsLoading } = useQuery<SnowflakeCredits[]>({
    queryKey: ["snowflake-credits", accessToken],
    queryFn: () => apiFetch("/admin/snowflake-credits", {}, accessToken),
    staleTime: SF_COST_STALE_MS,
    enabled: !!accessToken && isAdmin,
  })

  const { data: finances, isLoading: financesLoading } = useQuery<FinancesData>({
    queryKey: ["admin-finances", accessToken],
    queryFn: () => apiFetch("/admin/finances", {}, accessToken),
    staleTime: SF_COST_STALE_MS,
    enabled: !!accessToken && isAdmin,
  })

  const { data: dataQualityReports, isLoading: reportsLoading } = useQuery<DataQualityReport[]>({
    queryKey: ["admin-data-quality-reports", accessToken],
    queryFn: () => apiFetch("/admin/data-quality-reports", {}, accessToken),
    staleTime: 60_000,
    enabled: !!accessToken && isAdmin,
  })

  // NF-C0d — captured scoring terms are aggregate telemetry that only changes on a new import, so
  // a long staleTime (matching the SF-cost panels' reasoning above) avoids polling this on every
  // admin-tab focus for data that moves at import cadence, not request cadence.
  const { data: capturedTerms, isLoading: capturedTermsLoading } = useQuery<CapturedTermStat[]>({
    queryKey: ["fantasy-import-telemetry", accessToken],
    queryFn: () => apiFetch("/admin/fantasy-import-telemetry", {}, accessToken),
    staleTime: 300_000,
    enabled: !!accessToken && isAdmin,
  })

  const resolveMutation = useMutation({
    mutationFn: (reportId: string) =>
      apiFetch(`/admin/data-quality-reports/${reportId}/resolve`, { method: "PATCH" }, accessToken),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-data-quality-reports"] }),
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
                      <span className="block text-xs text-gray-500">
                        {m.target}
                        {m.ledger_behind && (
                          <span className="ml-1.5 text-amber-400">
                            · serving {m.version}, registry {m.registry_version} — reconcile ledger
                          </span>
                        )}
                      </span>
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
                    {["Month", "Compute cr.", "Cloud Svc cr.", "Billed cr.", "Est. Cost"].map((h) => (
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
                      <td className="py-3 pr-4 text-xs text-gray-300 whitespace-nowrap">{row.billed_credits.toFixed(1)}</td>
                      <td className="py-3 text-xs font-semibold text-[#10b981] whitespace-nowrap">
                        ${(row.billed_credits * 2).toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="mt-3 text-[10px] text-gray-600">
              Billed cr. applies Snowflake&apos;s cloud-services rule (free up to 10% of the day&apos;s compute, daily).
            </p>
          </section>
        </div>
        {/* Monthly P&L */}
        <section className="rounded-lg border border-[#262626] bg-[#141414] p-6">
          <div className="mb-5 flex items-center justify-between">
            <h2 className="text-base font-semibold text-white">Monthly P&amp;L</h2>
            <div className="flex items-center gap-4">
              <button
                onClick={() => setShowAwsBreakdown((v) => !v)}
                className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 transition-colors"
              >
                AWS breakdown
                {showAwsBreakdown ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              </button>
              <button
                onClick={() => setShowFixedBreakdown((v) => !v)}
                className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 transition-colors"
              >
                Fixed breakdown
                {showFixedBreakdown ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              </button>
            </div>
          </div>

          {showAwsBreakdown && finances?.aws_breakdown && Object.keys(finances.aws_breakdown).length > 0 && (
            <div className="mb-5 rounded-lg border border-[#1e1e1e] bg-[#0a0a0a] p-4">
              <p className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-gray-500">
                AWS Cost by Service (window total)
              </p>
              <ul className="space-y-1.5">
                {Object.entries(finances.aws_breakdown)
                  .sort((a, b) => b[1] - a[1])
                  .map(([name, cost]) => (
                    <li key={name} className="flex justify-between text-sm">
                      <span className="text-gray-400">{name}</span>
                      <span className="text-white">${cost.toFixed(2)}</span>
                    </li>
                  ))}
                <li className="flex justify-between border-t border-[#262626] pt-2 text-sm font-medium">
                  <span className="text-gray-300">Total AWS</span>
                  <span className="text-white">
                    ${Object.values(finances.aws_breakdown).reduce((a, b) => a + b, 0).toFixed(2)}
                  </span>
                </li>
              </ul>
              <p className="mt-2 text-[10px] text-gray-600">
                From Cost Explorer (grouped by service). Railway is cancelled and Dagster is self-hosted on EC2 —
                that spend now appears in the EC2 line.
              </p>
            </div>
          )}

          {showFixedBreakdown && finances && (() => {
            // E9.62 — fixed costs are per-month (a plan upgrade can cover only some months).
            // Prefer the per-month map; fall back to the flat dict when the backend predates
            // this change (deploy skew: this page ships before the Lambda does).
            const byMonth = finances.fixed_breakdown_by_month ?? {}
            const perMonthCols = Object.keys(byMonth).sort()
            const flat = finances.fixed_breakdown ?? {}
            if (perMonthCols.length === 0 && Object.keys(flat).length === 0) return null

            // Union of item names across months — an item present in only some months still
            // gets a row (rendered "—" where it doesn't apply).
            const items = perMonthCols.length
              ? Array.from(new Set(perMonthCols.flatMap((m) => Object.keys(byMonth[m] ?? {}))))
              : Object.keys(flat)

            return (
              <div className="mb-5 overflow-x-auto rounded-lg border border-[#1e1e1e] bg-[#0a0a0a] p-4">
                <p className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-gray-500">
                  Fixed Monthly Costs {perMonthCols.length > 0 && "(by month)"}
                </p>
                {perMonthCols.length === 0 ? (
                  <ul className="space-y-1.5">
                    {items.map((name) => (
                      <li key={name} className="flex justify-between text-sm">
                        <span className="text-gray-400">{name}</span>
                        <span className="text-white">${(flat[name] ?? 0).toFixed(2)}</span>
                      </li>
                    ))}
                    <li className="flex justify-between border-t border-[#262626] pt-2 text-sm font-medium">
                      <span className="text-gray-300">Total Fixed</span>
                      <span className="text-white">
                        ${Object.values(flat).reduce((a, b) => a + b, 0).toFixed(2)}/mo
                      </span>
                    </li>
                  </ul>
                ) : (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-[#262626]">
                        <th className="pb-2 pr-4 text-left text-[11px] font-semibold uppercase tracking-widest text-gray-500">
                          Item
                        </th>
                        {perMonthCols.map((m) => (
                          <th key={m} className="pb-2 pr-4 text-right text-[11px] font-semibold uppercase tracking-widest text-gray-500 whitespace-nowrap last:pr-0">
                            {m}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#1a1a1a]">
                      {items.map((name) => (
                        <tr key={name}>
                          <td className="py-1.5 pr-4 text-gray-400 whitespace-nowrap">{name}</td>
                          {perMonthCols.map((m) => {
                            const cost = byMonth[m]?.[name]
                            return (
                              <td key={m} className="py-1.5 pr-4 text-right text-white whitespace-nowrap last:pr-0">
                                {cost === undefined ? "—" : `$${cost.toFixed(2)}`}
                              </td>
                            )
                          })}
                        </tr>
                      ))}
                      <tr className="border-t border-[#262626] font-medium">
                        <td className="pt-2 pr-4 text-gray-300 whitespace-nowrap">Total Fixed</td>
                        {perMonthCols.map((m) => (
                          <td key={m} className="pt-2 pr-4 text-right text-white whitespace-nowrap last:pr-0">
                            ${Object.values(byMonth[m] ?? {}).reduce((a, b) => a + b, 0).toFixed(2)}
                          </td>
                        ))}
                      </tr>
                    </tbody>
                  </table>
                )}
                <p className="mt-2 text-[10px] text-gray-600">
                  A plan change applies only to the months it covers (an upgraded price replaces the
                  base, it is not added to it). Domain registration is not listed here — it is billed
                  through Route 53 and already appears in the AWS &ldquo;Other AWS&rdquo; line.
                </p>
              </div>
            )
          })()}

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
                      {["Month", "Fixed", "Snowflake", "AWS", "SES", "Vercel", "Total Cost", "Betting P&L", "Subs", "Net"].map((h) => (
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
                        <td className="py-3 pr-4 text-xs text-gray-400 whitespace-nowrap">{fmt(m.ses_cost)}</td>
                        {/* `?? null` — an un-deployed backend omits the field entirely, and fmt()
                            only special-cases null, so raw undefined would print "$undefined". */}
                        <td className="py-3 pr-4 text-xs text-gray-400 whitespace-nowrap">{fmt(m.vercel_cost ?? null)}</td>
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
                          vercel: acc.vercel + (m.vercel_cost ?? 0),
                          total_cost: acc.total_cost + m.total_cost,
                          betting_pl: acc.betting_pl + m.betting_pl,
                          subs: acc.subs + m.subscription_revenue,
                          net: acc.net + m.net,
                        }),
                        { fixed: 0, vercel: 0, total_cost: 0, betting_pl: 0, subs: 0, net: 0 }
                      )
                      return (
                        <tr className="border-t-2 border-[#333] bg-[#0f0f0f]">
                          <td className="py-3 pr-4 text-xs font-bold text-gray-300 whitespace-nowrap uppercase tracking-widest">YTD Total</td>
                          <td className="py-3 pr-4 text-xs font-medium text-gray-300 whitespace-nowrap">${totals.fixed.toFixed(2)}</td>
                          <td className="py-3 pr-4 text-xs text-gray-500 whitespace-nowrap">—</td>
                          <td className="py-3 pr-4 text-xs text-gray-500 whitespace-nowrap">—</td>
                          <td className="py-3 pr-4 text-xs text-gray-500 whitespace-nowrap">—</td>
                          <td className="py-3 pr-4 text-xs font-medium text-gray-300 whitespace-nowrap">${totals.vercel.toFixed(2)}</td>
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

        {/* Fantasy Import — Captured Scoring Terms (NF-C0d) */}
        <section className="rounded-lg border border-[#262626] bg-[#141414] p-6">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-base font-semibold text-white">Captured Scoring Terms</h2>
          </div>
          <p className="mb-5 text-xs text-gray-500">
            Scoring settings our users&apos; leagues have that our board does not project, ranked by
            how much closing the gap would matter — occurrences across imports × the average point
            value the setting carries. Aggregate only: no user, team, or roster is recorded, just the
            rule and its weight. Feeds NF-C0e&apos;s priority order.
          </p>
          {capturedTermsLoading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-10 rounded bg-[#1a1a1a] animate-pulse" />
              ))}
            </div>
          ) : !capturedTerms || capturedTerms.length === 0 ? (
            <p className="text-sm text-gray-500">No captured-term telemetry recorded yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#262626] text-left text-[11px] font-semibold uppercase tracking-widest text-gray-500">
                    <th className="pb-3 pr-4">Platform</th>
                    <th className="pb-3 pr-4">Setting</th>
                    <th className="pb-3 pr-4 text-right">Seen in</th>
                    <th className="pb-3 pr-4 text-right">Avg weight</th>
                    <th className="pb-3 pr-4 text-right">Score</th>
                    <th className="pb-3">Last seen</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1e1e1e]">
                  {capturedTerms.map((t) => (
                    <tr key={`${t.platform}:${t.key}`} className="text-gray-300">
                      <td className="py-3 pr-4 text-xs capitalize whitespace-nowrap">{t.platform}</td>
                      <td className="py-3 pr-4 text-xs font-mono">{t.key}</td>
                      <td className="py-3 pr-4 text-right text-xs tabular-nums">
                        {t.occurrences} import{t.occurrences === 1 ? "" : "s"}
                      </td>
                      <td className="py-3 pr-4 text-right text-xs tabular-nums">
                        {t.avg_abs_weight.toFixed(2)}
                      </td>
                      <td className="py-3 pr-4 text-right text-xs font-semibold tabular-nums text-white">
                        {t.score.toFixed(2)}
                      </td>
                      <td className="py-3 whitespace-nowrap text-xs text-gray-500">
                        {t.last_seen_at
                          ? new Date(t.last_seen_at).toLocaleDateString("en-US", {
                              month: "short", day: "numeric", year: "numeric",
                            })
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

      </main>
    </div>
    </AdminGuard>
  )
}
