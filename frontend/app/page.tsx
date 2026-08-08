import Link from "next/link"
import { ArrowRight, Eye, FileText, Lock, ShieldCheck, Trash2, Wrench } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Nav } from "@/components/nav"
import { LandingFaqSection } from "@/components/landing-faq"
import { FeaturedFantasyPlayer } from "@/components/home/featured-fantasy-player"
import { PickOfTheDay } from "@/components/home/pick-of-the-day"
import { SIGNUP_HREF } from "@/lib/access"
import { TRACK_RECORD_TRUST_LINK } from "@/lib/fantasy-claim-copy"
import {
  FOOTER_CTA,
  HERO,
  METHOD,
  PRINCIPLES,
  ROADMAP_HEADING,
  ROADMAP_NOTE,
  SEASON_ROADMAP,
  VERTICALS,
} from "@/lib/home-copy"

/**
 * E9.46 — the home page as a POSITIONING page for the whole company.
 *
 * ══ THE STORY THE PAGE TELLS, IN ORDER (operator, 2026-08-08) ══════════════════════════════════
 *
 *   Betting intelligence · Fantasy decision tools
 *   "The number is only half the answer."       ← what we model, how sure we are, what to do
 *        ↓
 *   FANTASY PRODUCT PROOF                       ← real player, real projection, real uncertainty,
 *        ↓                                        real disagreement, real personalisation
 *   MLB PRODUCT PROOF                           ← model vs market consensus, uncertainty, record
 *        ↓
 *   "Sports models that admit what they don't know."   ← the four principles ARE the proof
 *        ↓
 *   What is live, and what is next
 *        ↓
 *   Common questions
 *
 * ⭐ FANTASY LEADS because it is the current acquisition priority — so the first substantive
 * demonstration after the hero is the fantasy card, not the MLB one. Both verticals still get a
 * peer door in the hero; the ORDER of the proofs is what changed.
 *
 * ⭐ "Sports models that admit what they don't know" was the hero H1 in the first cut and is now
 * the methodology heading, because the four cells beneath it are its evidence. A claim sitting
 * three screens above its own proof is a slogan; sitting on top of it, it is a thesis statement.
 *
 * ⛔ THE CLAIM RULE. `best_alpha = 0`. Neither vertical may claim an advantage over a market or a
 * competitor — not in the hero, not on a card, not in a season teaser. Every claim-bearing sentence
 * lives in `lib/home-copy.ts` or `lib/fantasy-claim-copy.ts` and is screened by
 * `betting_ml/tests/test_e9_46_home_copy.py`; the RENDERED page is scanned again by
 * `e2e/specs/home-positioning.spec.ts`, the only instrument that can see a static heading or CTA.
 *
 * ⭐ THIS PAGE IS STATIC. Both live blocks are client components, so no read at request time and
 * no read can leave the positioning blank.
 */

export const metadata = {
  title: "Credence Sports — betting intelligence and fantasy decision tools",
  description: HERO.subhead,
  openGraph: {
    title: "Credence Sports — betting intelligence and fantasy decision tools",
    description: HERO.subhead,
    images: ["/brand/logo-full.svg"],
  },
}

function HeroSection() {
  return (
    <section
      className="relative overflow-hidden border-b border-[#262626] py-20 md:py-28"
      style={{
        backgroundImage: `
          linear-gradient(rgba(16,185,129,0.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(16,185,129,0.03) 1px, transparent 1px)
        `,
        backgroundSize: "48px 48px",
      }}
    >
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 80% 60% at 50% 0%, rgba(10,10,10,0) 0%, #0a0a0a 80%)",
        }}
      />

      <div className="relative mx-auto max-w-5xl px-4">
        <div className="text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#10b981]">
            {HERO.eyebrow}
          </p>
          <h1 className="mt-5 text-balance text-4xl font-bold tracking-tight text-white sm:text-5xl md:text-6xl">
            {HERO.headline}
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-pretty text-base leading-relaxed text-gray-400 md:text-lg">
            {HERO.subhead}
          </p>
        </div>

        {/* ⭐ THE DUAL ENTRY. Peer cards in a `md:grid-cols-2`, not a primary/secondary split —
            the defect being fixed is a home page that read as one product. Fantasy is first in
            `VERTICALS`, so it is the left/top card as well as the first proof below. */}
        <div className="mt-12 grid gap-4 md:grid-cols-2">
          {VERTICALS.map((v) => (
            // `data-vertical` is a TEST HANDLE and is load-bearing, not decoration. Both CTA
            // labels also appear elsewhere on the page, so a spec that located a door by its link
            // text alone would go on passing with the whole card deleted — measured.
            <div
              key={v.key}
              data-vertical={v.key}
              className="flex flex-col rounded-xl border border-[#262626] bg-[#141414]/80 p-6 backdrop-blur-sm transition-colors hover:border-[#10b981]/40 md:p-7"
            >
              <div className="flex items-center gap-2">
                <span className="rounded bg-[#10b981]/15 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider text-[#10b981]">
                  {v.sport}
                </span>
                <span className="text-[11px] font-medium uppercase tracking-wider text-gray-500">
                  {v.surface}
                </span>
                <span className="ml-auto text-[11px] text-gray-600">{v.status}</span>
              </div>

              <h2 className="mt-4 text-balance text-xl font-bold text-white md:text-2xl">
                {v.headline}
              </h2>
              <p className="mt-3 flex-1 text-sm leading-relaxed text-gray-400">{v.detail}</p>

              <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2">
                <Button
                  asChild
                  className="bg-[#10b981] font-semibold text-[#0a0a0a] hover:bg-[#059669]"
                >
                  <Link href={v.cta.href}>
                    {v.cta.label}
                    <ArrowRight className="ml-1.5 h-4 w-4" />
                  </Link>
                </Button>

                {/* ⭐ THE TRUST LINK — the proof that earns the click, and deliberately NOT a
                    statistic (NF-TR1: a marketing surface links to the record, it never quotes its
                    number). `needsAccount` keeps the MLB one from being a small lie: every MLB
                    record endpoint 401s for an anonymous caller (verified 2026-08-08), so the link
                    is marked, while the fantasy record is genuinely open and says so. */}
                <Link
                  href={v.trust.href}
                  className="inline-flex items-center gap-1.5 text-sm text-gray-400 underline-offset-4 transition-colors hover:text-[#10b981] hover:underline"
                >
                  {v.trust.label}
                  {v.trust.needsAccount ? (
                    <span className="inline-flex items-center gap-1 text-[11px] text-gray-600">
                      <Lock className="h-3 w-3" />
                      members
                    </span>
                  ) : (
                    <span className="text-[11px] text-gray-600">(free, no account)</span>
                  )}
                </Link>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

const PRINCIPLE_ICONS = [Eye, ShieldCheck, Wrench, Trash2] as const

function MethodSection() {
  return (
    <section className="border-t border-[#262626] py-16 md:py-20">
      <div className="mx-auto max-w-5xl px-4">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-balance text-2xl font-bold text-white md:text-3xl">
            {METHOD.heading}
          </h2>
          <p className="mt-4 text-sm leading-relaxed text-gray-400">{METHOD.intro}</p>
        </div>
        <div className="mt-10 grid gap-px overflow-hidden rounded-xl bg-[#262626] sm:grid-cols-2">
          {PRINCIPLES.map(({ title, detail }, i) => {
            const Icon = PRINCIPLE_ICONS[i] ?? Eye
            return (
              <div key={title} className="flex flex-col gap-3 bg-[#141414] px-6 py-7">
                <div className="flex items-center gap-2">
                  <Icon className="h-4 w-4 shrink-0 text-[#10b981]" />
                  <span className="text-sm font-semibold text-white">{title}</span>
                </div>
                <p className="text-sm leading-relaxed text-gray-500">{detail}</p>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}

function SeasonRoadmapSection() {
  return (
    <section className="border-t border-[#262626] py-16 md:py-20">
      <div className="mx-auto max-w-3xl px-4">
        {/* Centred to match every other section heading on the page. It was left-aligned in the
            first cut, which broke the page's vertical rhythm for no design-system reason. */}
        <h2 className="text-balance text-center text-2xl font-bold text-white md:text-3xl">
          {ROADMAP_HEADING}
        </h2>

        <ul className="mt-8 divide-y divide-[#262626] border-y border-[#262626]">
          {SEASON_ROADMAP.map((row) => (
            <li
              key={`${row.sport}-${row.what}`}
              className="flex flex-wrap items-center gap-x-4 gap-y-1 py-4"
            >
              <span
                className={`w-16 shrink-0 text-xs font-bold uppercase tracking-wider ${
                  row.live ? "text-[#10b981]" : "text-gray-600"
                }`}
              >
                {row.sport}
              </span>
              <span className={`flex-1 text-sm ${row.live ? "text-gray-200" : "text-gray-500"}`}>
                {row.what}
              </span>
              {/* ⛔ A not-yet-live row is TEXT, never a link — E9.56c's dead `/pricing` CTA
                  wearing a friendlier label. */}
              <span
                className={`shrink-0 rounded px-2 py-0.5 text-[11px] font-medium ${
                  row.live
                    ? "bg-[#10b981]/10 text-[#10b981]"
                    : "border border-[#262626] text-gray-500"
                }`}
              >
                {row.when}
              </span>
            </li>
          ))}
        </ul>

        <p className="mt-6 text-sm leading-relaxed text-gray-500">{ROADMAP_NOTE}</p>
      </div>
    </section>
  )
}

/** The blog, demoted (operator decision, 2026-08-07) — a real content surface that no longer
 *  competes with the products for the home page. Static link, never a featured post. */
function SecondaryLinks() {
  return (
    <section className="border-t border-[#262626] py-8">
      <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-center gap-x-6 gap-y-2 px-4">
        <Link
          href="/blog"
          className="inline-flex items-center gap-1.5 text-xs text-gray-500 underline-offset-4 transition-colors hover:text-gray-300 hover:underline"
        >
          <FileText className="h-3.5 w-3.5" />
          Notes from the blog
        </Link>
        <Link
          href="/about"
          className="text-xs text-gray-500 underline-offset-4 transition-colors hover:text-gray-300 hover:underline"
        >
          How we think about this
        </Link>
        <Link
          href={TRACK_RECORD_TRUST_LINK.href}
          className="text-xs text-gray-500 underline-offset-4 transition-colors hover:text-gray-300 hover:underline"
        >
          {TRACK_RECORD_TRUST_LINK.label}
        </Link>
        <Link
          href="/changelog"
          className="text-xs text-gray-500 underline-offset-4 transition-colors hover:text-gray-300 hover:underline"
        >
          What we shipped recently
        </Link>
      </div>
    </section>
  )
}

function FooterCta() {
  return (
    <section className="border-t border-[#262626] py-20 md:py-24">
      <div className="mx-auto max-w-2xl px-4 text-center">
        <h2 className="text-balance text-3xl font-bold text-white md:text-4xl">
          {FOOTER_CTA.headline}
        </h2>
        <p className="mt-4 text-sm leading-relaxed text-gray-400">{FOOTER_CTA.detail}</p>

        <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
          <Button
            size="lg"
            asChild
            className="bg-[#10b981] font-semibold text-[#0a0a0a] hover:bg-[#059669]"
          >
            <Link href={SIGNUP_HREF}>Create a free account</Link>
          </Button>
          <Button
            variant="ghost"
            size="lg"
            asChild
            className="text-gray-400 hover:bg-[#141414] hover:text-white"
          >
            <Link href="/subscribe">See what a membership adds</Link>
          </Button>
        </div>

        <p className="mt-6 text-xs leading-relaxed text-gray-600">{FOOTER_CTA.disclaimer}</p>
      </div>
    </section>
  )
}

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] font-sans">
      <Nav />
      <main>
        <HeroSection />
        {/* ⭐ FANTASY PROOF FIRST — the acquisition priority gets the first demonstration. */}
        <FeaturedFantasyPlayer />
        {/* The MLB proof renders `id="today"`, which is the betting card's own CTA target
            (`VERTICALS[betting].cta.href`). That pairing is two string literals in two files, so it
            is pinned by navigation: `home-positioning.spec.ts` clicks the CTA and asserts it lands. */}
        <PickOfTheDay />
        <MethodSection />
        <SeasonRoadmapSection />
        <LandingFaqSection />
        <SecondaryLinks />
        <FooterCta />
      </main>
    </div>
  )
}
