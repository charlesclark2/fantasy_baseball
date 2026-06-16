import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { ProbabilityBar } from "@/components/probability-bar"
import { Nav } from "@/components/nav"
import { LandingFaqSection } from "@/components/landing-faq"
import { FeaturedPickExplanation, type PickDriver } from "@/components/pick-explanation-home"
import {
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Database,
  Eye,
  FlaskConical,
  Pencil,
  ShieldCheck,
  Zap,
} from "lucide-react"

// ---------------------------------------------------------------------------
// API types
// ---------------------------------------------------------------------------

type YesterdayResult = {
  matchup: string
  market_type: string
  outcome: string
}

type FeaturedPick = {
  game_pk: string | null
  matchup: string
  game_time_et: string
  market_type: string
  edge: number
  model_prob: number
  market_prob: number
  ci_low: number
  ci_high: number
  conviction_label: string
  ai_summary: string
  yesterday: YesterdayResult | null
  is_stale?: boolean
  is_preliminary?: boolean
  pick_date?: string | null
  home_team?: string | null
  away_team?: string | null
  pick_side?: string | null  // 'home'|'away' for h2h; 'over'|'under' for totals
  // Story 30.15 — model explanation
  model_narrative?: string | null
  top_drivers?: PickDriver[] | null
  served_tier?: string | null
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

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
            <a href="mailto:charlie@credencesports.com?subject=Beta%20Access%20Request">Request Access</a>
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

function FeaturedPickCard({ pick }: { pick: FeaturedPick }) {
  const edgeStr =
    pick.game_pk !== null && pick.edge != null
      ? "+" + Math.abs(pick.edge).toFixed(1) + "%"
      : ""

  // model_prob is always P(home wins) for h2h, or P(over) for totals.
  // When < 0.5 the pick is on the away team / under — flip to the picked side.
  const awayOrUnder = pick.model_prob != null && pick.model_prob < 0.5
  const displayModelProb = awayOrUnder && pick.model_prob != null ? 1 - pick.model_prob : pick.model_prob
  const displayMarketProb = awayOrUnder && pick.market_prob != null ? 1 - pick.market_prob : pick.market_prob
  const displayCiLow = awayOrUnder && pick.ci_high != null ? 1 - pick.ci_high : pick.ci_low
  const displayCiHigh = awayOrUnder && pick.ci_low != null ? 1 - pick.ci_low : pick.ci_high

  return (
    <section id="featured-pick" className="py-16 md:py-24">
      <div className="mx-auto max-w-2xl px-4">
        <div
          className="rounded-xl border border-[#262626] bg-[#141414] shadow-xl shadow-black/40"
          style={{ borderLeft: "3px solid #10b981" }}
        >
          <div className="p-6 md:p-8">
            {/* Header row */}
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-widest text-[#10b981]">
                {pick.is_stale && pick.pick_date
                  ? new Date(pick.pick_date + "T12:00:00").toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    }) + " Pick"
                  : "Today’s Pick"}
              </span>
              <span className="text-xs text-gray-500">
                {new Date().toLocaleDateString("en-US", {
                  month: "long",
                  day: "numeric",
                  year: "numeric",
                })}
              </span>
            </div>

            {/* Stale banner */}
            {pick.is_stale && pick.game_pk !== null && (
              <div className="mt-3 rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2">
                <p className="text-xs text-gray-400">
                  Today&apos;s analysis is processing — new picks arrive after lineup confirmation.
                </p>
              </div>
            )}

            {pick.game_pk === null ? (
              <p className="mt-6 text-sm leading-relaxed text-gray-400">
                No picks available right now — check back after ~9am ET when the morning pipeline runs.
              </p>
            ) : (
              <>
                {/* Matchup */}
                <div className="mt-4">
                  <h2 className="text-3xl font-bold tracking-tight text-white md:text-4xl">
                    {pick.matchup}
                  </h2>
                  {pick.pick_side && (
                    <p className="mt-1.5 text-base font-semibold text-[#10b981]">
                      {pick.market_type === "h2h"
                        ? `Picking: ${pick.pick_side === "home" ? pick.home_team : pick.away_team} to win`
                        : `Picking: ${pick.pick_side.charAt(0).toUpperCase() + pick.pick_side.slice(1)}`}
                    </p>
                  )}
                  <p className="mt-1 text-sm text-gray-500">{pick.game_time_et}</p>
                </div>

                {/* Market badge */}
                <div className="mt-4">
                  <Badge className="bg-blue-500/15 text-blue-400 border border-blue-500/25 text-sm font-medium">
                    {pick.market_type}
                  </Badge>
                </div>

                {/* Stat chips */}
                <div className="mt-5 flex flex-wrap gap-3">
                  {edgeStr && (
                    <div className="flex items-center gap-2 rounded-lg border border-[#262626] bg-[#0a0a0a] px-3 py-2">
                      <span className="text-xs uppercase tracking-wider text-gray-500">Edge</span>
                      <span className="font-mono text-sm font-bold text-[#10b981]">
                        {edgeStr}
                      </span>
                    </div>
                  )}
                  {displayModelProb != null && (
                    <div className="flex items-center gap-2 rounded-lg border border-[#262626] bg-[#0a0a0a] px-3 py-2">
                      <span className="text-xs uppercase tracking-wider text-gray-500">Model</span>
                      <span className="font-mono text-sm font-semibold text-white">
                        {(displayModelProb * 100).toFixed(1)}%
                      </span>
                    </div>
                  )}
                  {displayMarketProb != null && (
                    <div className="flex items-center gap-2 rounded-lg border border-[#262626] bg-[#0a0a0a] px-3 py-2">
                      <span className="text-xs uppercase tracking-wider text-gray-500">Market</span>
                      <span className="font-mono text-sm text-gray-400">
                        {(displayMarketProb * 100).toFixed(1)}%
                      </span>
                    </div>
                  )}
                </div>

                {/* Conviction / preliminary badge */}
                <div className="mt-5 flex flex-wrap gap-2">
                  {!pick.is_stale && pick.conviction_label && (
                    <Badge className="bg-[#10b981]/15 text-[#10b981] border border-[#10b981]/30 text-xs font-bold uppercase tracking-widest">
                      {pick.conviction_label}
                    </Badge>
                  )}
                  {pick.is_preliminary && (
                    <Badge className="bg-amber-500/15 text-amber-400 border border-amber-500/25 text-xs font-semibold">
                      Preliminary — Lineups Not Yet Confirmed
                    </Badge>
                  )}
                </div>

                {/* Probability bar */}
                {displayModelProb != null && displayMarketProb != null && (
                  <div className="mt-6">
                    <ProbabilityBar
                      ciLow={displayCiLow}
                      ciHigh={displayCiHigh}
                      modelProb={displayModelProb}
                      marketProb={displayMarketProb}
                      showHighConviction={false}
                    />
                  </div>
                )}

                {/* AI summary — hidden when model narrative is available */}
                {!pick.model_narrative && (
                  <p className="mt-6 text-sm leading-relaxed text-gray-400">
                    {pick.ai_summary}
                  </p>
                )}

                {/* Story 30.15 — model narrative + top drivers */}
                <FeaturedPickExplanation
                  narrative={pick.model_narrative}
                  topDrivers={pick.top_drivers}
                  servedTier={pick.served_tier}
                />

                {pick.yesterday && (
                  <>
                    <Separator className="my-6 bg-[#262626]" />
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <span className="text-xs text-gray-500">
                        <span className="text-gray-400 font-medium">Yesterday:</span>{" "}
                        {pick.yesterday.matchup}
                      </span>
                      <Badge className="bg-[#10b981]/10 text-[#10b981] border border-[#10b981]/25 text-xs">
                        <CheckCircle2 className="mr-1 h-3 w-3" />
                        {pick.yesterday.outcome}
                      </Badge>
                    </div>
                  </>
                )}
              </>
            )}
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

function WhyCredenceStrip() {
  const pillars = [
    {
      icon: Eye,
      title: "Transparent",
      description:
        "Every pick shows the model probability, market probability, and the full uncertainty range — not just a directional call.",
    },
    {
      icon: ShieldCheck,
      title: "Rigorous",
      description:
        "Only picks where the entire credible interval clears the market line reach the dashboard. Marginal calls stay out.",
    },
    {
      icon: BookOpen,
      title: "Shows its work",
      description:
        "Bayesian sub-models for pitching, offense, bullpen, and run environment — every factor is visible and labeled.",
    },
  ]

  return (
    <section className="border-y border-[#262626] py-10 md:py-14">
      <div className="mx-auto max-w-4xl px-4">
        <h2 className="text-balance text-center text-2xl font-bold text-white md:text-3xl mb-10">
          Why Credence
        </h2>
        <div className="grid gap-px bg-[#262626] sm:grid-cols-3 rounded-xl overflow-hidden">
          {pillars.map(({ icon: Icon, title, description }) => (
            <div
              key={title}
              className="flex flex-col gap-3 bg-[#141414] px-6 py-7"
            >
              <div className="flex items-center gap-2">
                <Icon className="h-4 w-4 shrink-0 text-[#10b981]" />
                <span className="text-sm font-semibold text-white">{title}</span>
              </div>
              <p className="text-sm leading-relaxed text-gray-500">{description}</p>
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

function LatestPost({ post }: { post: { post_id: string; title: string; excerpt?: string | null; published_at?: string | null } | null }) {
  if (!post) return null
  return (
    <section className="py-12 md:py-16 border-t border-[#262626]">
      <div className="mx-auto max-w-4xl px-4">
        <div className="flex items-center gap-2 mb-5">
          <Pencil className="h-4 w-4 text-[#10b981]" />
          <span className="text-xs uppercase tracking-widest text-[#10b981] font-semibold">
            From the Blog
          </span>
        </div>
        <Link
          href={`/blog/${post.post_id}`}
          className="group block rounded-xl border border-[#262626] bg-[#141414] p-6 hover:border-[#10b981]/30 transition-colors"
        >
          <h3 className="text-lg font-bold text-white group-hover:text-[#10b981] transition-colors">
            {post.title}
          </h3>
          {post.excerpt && (
            <p className="mt-2 text-sm leading-relaxed text-gray-400 line-clamp-2">{post.excerpt}</p>
          )}
          <p className="mt-3 text-xs text-[#10b981]">Read more →</p>
        </Link>
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
        <p className="mt-4 text-sm text-gray-400">
          Credence Sports is currently in private beta. Send an email to request access
          and we&apos;ll be in touch.
        </p>
        <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
          <Button
            size="lg"
            asChild
            className="bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
          >
            <a href="mailto:charlie@credencesports.com?subject=Beta%20Access%20Request">Request Access</a>
          </Button>
          <Button
            variant="ghost"
            size="lg"
            asChild
            className="text-gray-400 hover:text-white hover:bg-[#141414]"
          >
            <Link href="/login">Sign In</Link>
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

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function LandingPage() {
  const base = process.env.NEXT_PUBLIC_API_URL ?? ""

  const [featuredRes, blogData] = await Promise.all([
    base
      ? fetch(`${base}/picks/featured`, { cache: "no-store" })
          .then((r) => (r.ok ? r.json() : { game_pk: null }))
          .catch(() => ({ game_pk: null }))
      : Promise.resolve({ game_pk: null }),
    base
      ? fetch(`${base}/blog/posts`, { cache: "no-store" })
          .then((r) => (r.ok ? r.json() : { posts: [] }))
          .catch(() => ({ posts: [] }))
      : Promise.resolve({ posts: [] }),
  ])

  const latestPost = (blogData.posts ?? [])[0] ?? null

  return (
    <div className="min-h-screen bg-[#0a0a0a] font-sans">
      <Nav />
      <main>
        <HeroSection />
        <LatestPost post={latestPost} />
        <FeaturedPickCard pick={featuredRes as FeaturedPick} />
        <WhyCredenceStrip />
        <HowItWorks />
        <TrustSection />
        <LandingFaqSection />
        <FooterCta />
      </main>
    </div>
  )
}
