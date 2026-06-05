import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { ProbabilityBar } from "@/components/probability-bar"
import {
  CheckCircle2,
  ChevronDown,
  Database,
  FlaskConical,
  Zap,
} from "lucide-react"

// ---------------------------------------------------------------------------
// MOCK DATA — replace with API calls when backend is wired up
// ---------------------------------------------------------------------------
export const MOCK_DATA = {
  todaysPick: {
    matchup: "HOU @ NYM",
    gameTime: "7:10 PM ET",
    market: "Totals Over 8.5",
    edge: "+4.2%",
    modelProb: 0.583,
    marketProb: 0.541,
    ciLow: 0.48,
    ciHigh: 0.61,
    conviction: "HIGH CONVICTION" as const,
    justification:
      "Starter suppression signals are elevated — Houston's rotation carries a significant xwOBA advantage over NYM's lineup in this matchup. The 80% credible interval sits entirely above the Bovada implied probability, satisfying the high-conviction gate.",
  },
  yesterdaysResult: {
    label: "Yesterday",
    matchup: "NYY @ BOS Under 8.0",
    outcome: "Won" as const,
  },
  trackRecord: {
    totalPicks: 247,
    winRate: "54.3%",
    meanClv: "+2.1%",
    netPnl: "+$312",
  },
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Navbar() {
  return (
    <nav className="sticky top-0 z-50 border-b border-[#262626] bg-[#0a0a0a]/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        {/* Wordmark */}
        <Link href="/" className="flex items-center gap-0 text-lg font-bold tracking-tight">
          <span className="text-[#10b981]">Credence</span>
          <span className="text-white"> Sports</span>
        </Link>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            asChild
            className="text-gray-400 hover:text-white hover:bg-[#141414]"
          >
            <Link href="/login">Sign In</Link>
          </Button>
          <Button
            size="sm"
            asChild
            className="bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
          >
            <Link href="/login">Join Beta</Link>
          </Button>
        </div>
      </div>
    </nav>
  )
}

function HeroSection() {
  return (
    <section
      className="relative overflow-hidden border-b border-[#262626] py-24 md:py-36"
      style={{
        backgroundImage: `
          linear-gradient(rgba(16,185,129,0.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(16,185,129,0.03) 1px, transparent 1px)
        `,
        backgroundSize: "48px 48px",
      }}
    >
      {/* Subtle radial fade over the grid */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 80% 60% at 50% 0%, rgba(10,10,10,0) 0%, #0a0a0a 80%)",
        }}
      />

      <div className="relative mx-auto max-w-4xl px-4 text-center">
        <h1 className="text-balance text-5xl font-bold tracking-tight text-white md:text-7xl">
          Daily edge,{" "}
          <span className="text-[#10b981]">quantified.</span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-pretty text-lg leading-relaxed text-gray-400 md:text-xl">
          Bayesian sports analytics that shows its work — model probability,
          uncertainty range, and the reasoning behind every pick.
        </p>

        <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Button
            size="lg"
            asChild
            className="w-full bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669] sm:w-auto"
          >
            <Link href="/login">Join Beta</Link>
          </Button>
          <Button
            variant="outline"
            size="lg"
            asChild
            className="w-full border-[#262626] bg-transparent text-gray-300 hover:bg-[#141414] hover:text-white sm:w-auto"
          >
            <a href="#featured-pick">
              See Today&apos;s Pick
              <ChevronDown className="ml-2 h-4 w-4" />
            </a>
          </Button>
        </div>
      </div>
    </section>
  )
}

function FeaturedPickCard() {
  const { todaysPick: pick, yesterdaysResult: yesterday } = MOCK_DATA

  return (
    <section id="featured-pick" className="py-16 md:py-24">
      <div className="mx-auto max-w-2xl px-4">
        <div className="rounded-xl border border-[#262626] bg-[#141414] shadow-xl shadow-black/40"
          style={{ borderLeft: "3px solid #10b981" }}
        >
          <div className="p-6 md:p-8">
            {/* Header row */}
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-widest text-[#10b981]">
                Today&apos;s Pick
              </span>
              <span className="text-xs text-gray-500">
                {new Date().toLocaleDateString("en-US", {
                  month: "long",
                  day: "numeric",
                  year: "numeric",
                })}
              </span>
            </div>

            {/* Matchup */}
            <div className="mt-4">
              <h2 className="text-3xl font-bold tracking-tight text-white md:text-4xl">
                {pick.matchup}
              </h2>
              <p className="mt-1 text-sm text-gray-500">{pick.gameTime}</p>
            </div>

            {/* Market badge */}
            <div className="mt-4">
              <Badge className="bg-blue-500/15 text-blue-400 border border-blue-500/25 text-sm font-medium">
                {pick.market}
              </Badge>
            </div>

            {/* Stat chips */}
            <div className="mt-5 flex flex-wrap gap-3">
              <div className="flex items-center gap-2 rounded-lg border border-[#262626] bg-[#0a0a0a] px-3 py-2">
                <span className="text-xs uppercase tracking-wider text-gray-500">Edge</span>
                <span className="font-mono text-sm font-bold text-[#10b981]">
                  {pick.edge}
                </span>
              </div>
              <div className="flex items-center gap-2 rounded-lg border border-[#262626] bg-[#0a0a0a] px-3 py-2">
                <span className="text-xs uppercase tracking-wider text-gray-500">Model</span>
                <span className="font-mono text-sm font-semibold text-white">
                  {(pick.modelProb * 100).toFixed(1)}%
                </span>
              </div>
              <div className="flex items-center gap-2 rounded-lg border border-[#262626] bg-[#0a0a0a] px-3 py-2">
                <span className="text-xs uppercase tracking-wider text-gray-500">Market</span>
                <span className="font-mono text-sm text-gray-400">
                  {(pick.marketProb * 100).toFixed(1)}%
                </span>
              </div>
            </div>

            {/* Conviction badge */}
            <div className="mt-5">
              <Badge className="bg-[#10b981]/15 text-[#10b981] border border-[#10b981]/30 text-xs font-bold uppercase tracking-widest">
                {pick.conviction}
              </Badge>
            </div>

            {/* Probability bar */}
            <div className="mt-6">
              <ProbabilityBar
                ciLow={pick.ciLow}
                ciHigh={pick.ciHigh}
                modelProb={pick.modelProb}
                marketProb={pick.marketProb}
              />
            </div>

            {/* Justification */}
            <p className="mt-6 text-sm leading-relaxed text-gray-400">
              {pick.justification}
            </p>

            <Separator className="my-6 bg-[#262626]" />

            {/* Yesterday's result */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="text-xs text-gray-500">
                <span className="text-gray-400 font-medium">{yesterday.label}:</span>{" "}
                {yesterday.matchup}
              </span>
              <Badge className="bg-[#10b981]/10 text-[#10b981] border border-[#10b981]/25 text-xs">
                <CheckCircle2 className="mr-1 h-3 w-3" />
                Won
              </Badge>
            </div>
          </div>
        </div>

        {/* CTA below card */}
        <p className="mt-4 text-center text-sm text-gray-600">
          <Link
            href="/login"
            className="text-gray-500 underline-offset-4 hover:text-[#10b981] hover:underline transition-colors"
          >
            Sign in to see all picks &rarr;
          </Link>
        </p>
      </div>
    </section>
  )
}

function TrackRecordStrip() {
  const tr = MOCK_DATA.trackRecord

  const stats = [
    { label: "Total Picks", value: tr.totalPicks.toString(), accent: false },
    { label: "Win Rate", value: tr.winRate, accent: false },
    { label: "Mean CLV", value: tr.meanClv, accent: true },
    { label: "Net P&L", value: tr.netPnl, accent: true },
  ]

  return (
    <section className="py-10 md:py-14 border-y border-[#262626]">
      <div className="mx-auto max-w-4xl px-4">
        <div className="grid grid-cols-2 gap-px bg-[#262626] rounded-xl overflow-hidden sm:grid-cols-4">
          {stats.map((stat) => (
            <div
              key={stat.label}
              className="flex flex-col items-center justify-center bg-[#141414] px-6 py-6 gap-1"
            >
              <span
                className={`text-2xl font-bold font-mono tracking-tight ${
                  stat.accent ? "text-[#10b981]" : "text-white"
                }`}
              >
                {stat.value}
              </span>
              <span className="text-xs uppercase tracking-wider text-gray-500">
                {stat.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function HowItWorks() {
  const steps = [
    {
      num: "01",
      title: "Data",
      icon: Database,
      description:
        "Statcast pitch data, live odds feeds, and confirmed lineup data form the foundation of every analysis run.",
    },
    {
      num: "02",
      title: "Model",
      icon: FlaskConical,
      description:
        "Bayesian sub-models quantify uncertainty across run environment, pitching, offense, and bullpen — producing a credible interval, not just a point estimate.",
    },
    {
      num: "03",
      title: "Signal",
      icon: Zap,
      description:
        "Only picks where the full credible interval clears the market line reach your dashboard. No marginal calls.",
    },
  ]

  return (
    <section className="py-16 md:py-24">
      <div className="mx-auto max-w-4xl px-4">
        <h2 className="text-balance text-center text-2xl font-bold text-white md:text-3xl">
          How it works
        </h2>
        <div className="mt-12 grid gap-6 md:grid-cols-3">
          {steps.map((step) => {
            const Icon = step.icon
            return (
              <div
                key={step.num}
                className="rounded-xl border border-[#262626] bg-[#141414] p-6"
              >
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs font-bold text-[#10b981]">
                    {step.num}
                  </span>
                  <Icon className="h-4 w-4 text-[#10b981]" />
                  <span className="font-semibold text-white">{step.title}</span>
                </div>
                <p className="mt-4 text-sm leading-relaxed text-gray-400">
                  {step.description}
                </p>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}

function TrustSection() {
  return (
    <section className="py-10 md:py-14 border-t border-[#262626]">
      <div className="mx-auto max-w-2xl px-4">
        <div className="rounded-xl border border-[#262626] bg-[#141414] p-8 md:p-10">
          <p className="text-pretty text-base leading-relaxed text-gray-300 md:text-lg">
            Credence Sports shows every losing bet. Win rate, mean CLV, and P&amp;L
            are calculated from all qualified picks — not a curated subset. The
            model&apos;s uncertainty is always visible.
          </p>
        </div>
      </div>
    </section>
  )
}

function FooterCta() {
  return (
    <section className="py-20 md:py-28 border-t border-[#262626]">
      <div className="mx-auto max-w-2xl px-4 text-center">
        <h2 className="text-balance text-3xl font-bold text-white md:text-4xl">
          Ready to see every pick?
        </h2>
        <div className="mt-8">
          <Button
            size="lg"
            asChild
            className="bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
          >
            <Link href="/login">Join Beta</Link>
          </Button>
        </div>
        <p className="mt-6 text-xs leading-relaxed text-gray-600">
          Picks are informational only and do not constitute financial advice.
          You are solely responsible for any wagers placed.
        </p>
      </div>
    </section>
  )
}

function Footer() {
  return (
    <footer className="border-t border-[#262626] bg-[#0a0a0a]">
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-4 px-4 py-8 sm:flex-row sm:justify-between">
        {/* Wordmark */}
        <span className="text-sm font-bold">
          <span className="text-[#10b981]">Credence</span>
          <span className="text-white"> Sports</span>
        </span>

        {/* Copyright */}
        <span className="text-xs text-gray-600">
          &copy; 2026 Penumbra Partners
        </span>

        {/* Links */}
        <nav className="flex items-center gap-4">
          {["Privacy Policy", "Terms", "Contact"].map((label) => (
            <Link
              key={label}
              href="/login"
              className="text-xs text-gray-600 hover:text-gray-400 transition-colors"
            >
              {label}
            </Link>
          ))}
        </nav>
      </div>
    </footer>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] font-sans">
      <Navbar />
      <main>
        <HeroSection />
        <FeaturedPickCard />
        <TrackRecordStrip />
        <HowItWorks />
        <TrustSection />
        <FooterCta />
      </main>
      <Footer />
    </div>
  )
}
