"use client"

import Link from "next/link"
import { LogOut, Lock, RefreshCw } from "lucide-react"
import { useState } from "react"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  Cell,
} from "recharts"
import { Button } from "@/components/ui/button"

// TODO: replace with useQuery hooks — GET /admin/pipeline-status and GET /admin/model-freshness
const MOCK_DATA = {
  statusCards: [
    {
      label: "Last Dagster Run",
      value: "8:14 AM EDT",
      subtitle: "Today — completed successfully",
      status: "healthy",
    },
    {
      label: "Predictions Generated",
      value: "14 of 15",
      subtitle: "games today — 1 postponed",
      status: "healthy",
    },
    {
      label: "CLV Label Count",
      value: "73 / 100",
      subtitle: "Gate threshold — 27 labels needed",
      status: "watch",
    },
    {
      label: "Stale Signals",
      value: "None",
      subtitle: "All signals fresh for today",
      status: "healthy",
    },
    {
      label: "Snowflake Credits MTD",
      value: "31.2 / 120",
      subtitle: "26% of monthly cap used",
      status: "healthy",
    },
    {
      label: "Signal Completeness",
      value: "0.94",
      subtitle: "Score above 0.80 threshold",
      status: "healthy",
    },
  ],
  pipelineRuns: [
    {
      timestamp: "Jun 5, 8:14 AM",
      job: "daily_ingestion_job",
      duration: "4m 32s",
      status: "success",
      notes: "14 predictions generated",
    },
    {
      timestamp: "Jun 5, 8:02 AM",
      job: "lineup_monitor_sensor",
      duration: "0m 12s",
      status: "success",
      notes: "Lineups confirmed — rerun triggered",
    },
    {
      timestamp: "Jun 4, 8:19 AM",
      job: "daily_ingestion_job",
      duration: "5m 01s",
      status: "success",
      notes: "13 predictions generated",
    },
    {
      timestamp: "Jun 4, 8:04 AM",
      job: "lineup_monitor_sensor",
      duration: "0m 09s",
      status: "success",
      notes: "Lineups confirmed",
    },
    {
      timestamp: "Jun 3, 8:31 AM",
      job: "daily_ingestion_job",
      duration: "6m 14s",
      status: "warning",
      notes:
        "Signal completeness 0.71 — below threshold, predictions generated with warning",
    },
    {
      timestamp: "Jun 3, 7:58 AM",
      job: "lineup_monitor_sensor",
      duration: "0m 11s",
      status: "success",
      notes: "Lineups confirmed",
    },
    {
      timestamp: "Jun 2, 8:15 AM",
      job: "daily_ingestion_job",
      duration: "4m 48s",
      status: "success",
      notes: "12 predictions generated",
    },
    {
      timestamp: "Jun 1, 9:02 AM",
      job: "daily_ingestion_job",
      duration: "2m 11s",
      status: "failed",
      notes:
        "Parlay API timeout — no predictions generated. Manual rerun at 9:47 AM succeeded.",
    },
  ],
  modelArtifacts: [
    {
      model: "Run Environment v2",
      lastTrained: "May 28, 2026",
      daysAgo: 8,
      status: "healthy",
    },
    {
      model: "Offense Model v2",
      lastTrained: "May 28, 2026",
      daysAgo: 8,
      status: "healthy",
    },
    {
      model: "Starter Quality v1",
      lastTrained: "May 14, 2026",
      daysAgo: 22,
      status: "watch",
    },
    {
      model: "Starter IP Model v1",
      lastTrained: "May 14, 2026",
      daysAgo: 22,
      status: "watch",
    },
    {
      model: "Bullpen State v2",
      lastTrained: "May 28, 2026",
      daysAgo: 8,
      status: "healthy",
    },
  ],
  creditData: [
    { date: "May 30", credits: 2.1 },
    { date: "May 31", credits: 3.8 },
    { date: "Jun 1", credits: 1.2 },
    { date: "Jun 2", credits: 2.9 },
    { date: "Jun 3", credits: 4.7 },
    { date: "Jun 4", credits: 3.1 },
    { date: "Jun 5", credits: 1.8 },
  ],
}

function statusColor(status: string): string {
  if (status === "healthy") return "#10b981"
  if (status === "watch") return "#f59e0b"
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
    success:
      "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30",
    warning: "bg-amber-500/15 text-amber-400 border border-amber-500/30",
    failed: "bg-red-500/15 text-red-400 border border-red-500/30",
  }
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium uppercase tracking-wide ${styles[status] ?? styles.success}`}
    >
      {status}
    </span>
  )
}

export default function AdminPage() {
  const [refreshState, setRefreshState] = useState<
    "idle" | "loading" | "done"
  >("idle")

  function handleRefresh() {
    setRefreshState("loading")
    setTimeout(() => setRefreshState("done"), 2000)
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a] font-sans">
      {/* Nav */}
      <nav className="sticky top-0 z-50 border-b border-[#262626] bg-[#0a0a0a]/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
          <Link
            href="/"
            className="flex items-center gap-0 text-lg font-bold tracking-tight"
          >
            <span className="text-[#10b981]">Credence</span>
            <span className="text-white"> Sports</span>
          </Link>
          <div className="flex items-center gap-3">
            <span className="hidden text-xs text-gray-500 sm:block">
              user@example.com
            </span>
            <Button
              variant="ghost"
              size="sm"
              className="text-gray-400 hover:text-white hover:bg-[#141414]"
              asChild
            >
              <Link href="/">
                <LogOut className="mr-1.5 h-3.5 w-3.5" />
                Sign Out
              </Link>
            </Button>
          </div>
        </div>
        {/* Sub-nav — Admin active */}
        <div className="mx-auto flex max-w-6xl gap-6 px-4 pb-0">
          <Link
            href="/dashboard"
            className="border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
          >
            Dashboard
          </Link>
          <Link
            href="/performance"
            className="border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
          >
            Performance
          </Link>
          <Link
            href="/settings"
            className="border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
          >
            Settings
          </Link>
          <Link
            href="/admin"
            className="border-b-2 border-[#10b981] pb-2.5 text-sm text-white font-medium transition-colors"
          >
            Admin
          </Link>
        </div>
      </nav>

      <main className="mx-auto max-w-6xl px-4 py-8 space-y-8">
        {/* 1. Page header */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">
              System Health
            </h1>
            <p className="mt-1 flex items-center gap-1.5 text-sm text-gray-500">
              <Lock className="h-3.5 w-3.5 text-red-500 flex-shrink-0" />
              Pipeline status and model freshness — admin only
            </p>
          </div>
          <span className="text-sm text-gray-500 pt-1">June 5, 2026</span>
        </div>

        {/* 2 & 3. Status cards + force refresh */}
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-widest text-gray-500">
              Status Overview
            </h2>
            <div className="flex items-center gap-3">
              {refreshState === "done" && (
                <span className="text-sm text-[#10b981]">
                  Refresh triggered — Dagster job queued
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
                {refreshState === "loading"
                  ? "Refreshing..."
                  : "Force Refresh Predictions"}
              </Button>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {MOCK_DATA.statusCards.map((card) => (
              <div
                key={card.label}
                className="rounded-lg bg-[#141414] p-5"
                style={{
                  borderLeft: `2px solid ${statusColor(card.status)}`,
                  border: `1px solid #262626`,
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
        </section>

        {/* 4. Pipeline run log */}
        <section className="rounded-lg border border-[#262626] bg-[#141414] p-6">
          <h2 className="mb-5 text-base font-semibold text-white">
            Recent Pipeline Runs
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#262626]">
                  <th className="pb-3 text-left text-xs font-semibold uppercase tracking-widest text-gray-500">
                    Timestamp
                  </th>
                  <th className="pb-3 text-left text-xs font-semibold uppercase tracking-widest text-gray-500">
                    Job
                  </th>
                  <th className="pb-3 text-left text-xs font-semibold uppercase tracking-widest text-gray-500">
                    Duration
                  </th>
                  <th className="pb-3 text-left text-xs font-semibold uppercase tracking-widest text-gray-500">
                    Status
                  </th>
                  <th className="pb-3 text-left text-xs font-semibold uppercase tracking-widest text-gray-500">
                    Notes
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1a1a1a]">
                {MOCK_DATA.pipelineRuns.map((run, i) => (
                  <tr
                    key={i}
                    className={
                      run.status === "failed"
                        ? "bg-red-500/5"
                        : "hover:bg-[#1a1a1a]"
                    }
                  >
                    <td className="py-3 pr-4 font-mono text-xs text-gray-400 whitespace-nowrap">
                      {run.timestamp}
                    </td>
                    <td className="py-3 pr-4 font-mono text-xs text-gray-300 whitespace-nowrap">
                      {run.job}
                    </td>
                    <td className="py-3 pr-4 text-xs text-gray-400 whitespace-nowrap">
                      {run.duration}
                    </td>
                    <td className="py-3 pr-4 whitespace-nowrap">
                      <RunBadge status={run.status} />
                    </td>
                    <td className="py-3 text-xs text-gray-500 max-w-xs">
                      {run.notes}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* 5 & 6. Model freshness + credit chart side by side on desktop */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* 5. Model freshness */}
          <section className="rounded-lg border border-[#262626] bg-[#141414] p-6">
            <h2 className="mb-5 text-base font-semibold text-white">
              Model Artifact Freshness
            </h2>
            <ul className="space-y-3">
              {MOCK_DATA.modelArtifacts.map((artifact) => (
                <li
                  key={artifact.model}
                  className="flex items-center justify-between gap-4 py-2 border-b border-[#1e1e1e] last:border-0"
                >
                  <span className="text-sm text-white font-medium flex-shrink-0">
                    {artifact.model}
                  </span>
                  <span className="text-xs text-gray-500 text-center flex-1">
                    Last trained: {artifact.lastTrained}{" "}
                    <span
                      style={{
                        color:
                          artifact.status === "watch"
                            ? "#f59e0b"
                            : "#6b7280",
                      }}
                    >
                      ({artifact.daysAgo} days ago)
                    </span>
                  </span>
                  <StatusDot status={artifact.status} />
                </li>
              ))}
            </ul>
          </section>

          {/* 6. Snowflake credit chart */}
          <section className="rounded-lg border border-[#262626] bg-[#141414] p-6">
            <h2 className="mb-5 text-base font-semibold text-white">
              Snowflake Credit Usage (Last 7 Days)
            </h2>
            <BarChart
              width={440}
              height={160}
              data={MOCK_DATA.creditData}
              margin={{ top: 4, right: 8, left: -16, bottom: 0 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#262626"
                vertical={false}
              />
              <XAxis
                dataKey="date"
                tick={{ fill: "#6b7280", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                dy={6}
              />
              <YAxis
                tick={{ fill: "#6b7280", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                domain={[0, 6]}
                ticks={[0, 2, 4, 6]}
              />
              <Tooltip
                contentStyle={{
                  background: "#141414",
                  border: "1px solid #262626",
                  borderRadius: "6px",
                  color: "#fff",
                  fontSize: "12px",
                }}
                formatter={(v: number) => [`${v} credits`, "Usage"]}
                cursor={{ fill: "#1a1a1a" }}
              />
              <ReferenceLine
                y={4}
                stroke="#ef4444"
                strokeDasharray="4 3"
                strokeWidth={1.5}
                label={{
                  value: "Daily budget (4 credits)",
                  fill: "#ef4444",
                  fontSize: 10,
                  position: "insideTopRight",
                }}
              />
              <Bar dataKey="credits" radius={[3, 3, 0, 0]}>
                {MOCK_DATA.creditData.map((entry, index) => (
                  <Cell
                    key={index}
                    fill={entry.credits > 4 ? "#f59e0b" : "#10b981"}
                  />
                ))}
              </Bar>
            </BarChart>
          </section>
        </div>
      </main>
    </div>
  )
}
