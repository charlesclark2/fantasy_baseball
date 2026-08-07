import Link from "next/link"
import { ArrowRight, Eye, FileText, Lock, ShieldCheck, Trash2, Wrench } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Nav } from "@/components/nav"
import { LandingFaqSection } from "@/components/landing-faq"
import { PickOfTheDay } from "@/components/home/pick-of-the-day"
import { SIGNUP_HREF } from "@/lib/access"
import { DISAGREEMENT_HOOK, TRACK_RECORD_TRUST_LINK } from "@/lib/fantasy-claim-copy"
import {
  FOOTER_CTA,
  HERO,
  HONESTY_STATEMENT,
  PRINCIPLES,
  ROADMAP_NOTE,
  SEASON_ROADMAP,
  VERTICALS,
} from "@/lib/home-copy"

/**
 * E9.46 — the home page as a POSITIONING page for the whole company.
 *
 * ══ WHAT CHANGED AND WHY ══════════════════════════════════════════════════════════════════════
 *
 * It used to be an MLB-betting landing page ("Daily edge, quantified") with the blog above the
 * fold. Credence is now two products — betting intelligence for MLB, fantasy for the NFL — and a
 * visitor arriving for either one had to work out from an MLB pick card whether they were in the
 * right place. So: one platform identity, a FIRST-CLASS DOOR to each vertical, and the blog
 * demoted out of the hero and out of the primary nav (operator decision, 2026-08-07).
 *
 * ⛔ THE CLAIM RULE, WHICH IS THE WHOLE STORY. `best_alpha = 0`. Neither vertical may claim an
 * advantage over a market or a competitor — not in the hero, not on a card, not in a season
 * teaser. Every claim-bearing sentence on this page lives in `lib/home-copy.ts` or
 * `lib/fantasy-claim-copy.ts` and is screened by `betting_ml/tests/test_e9_46_home_copy.py`; the
 * RENDERED page is scanned again by `e2e/specs/home-positioning.spec.ts`, which is the only
 * instrument that can see a static heading or CTA no export-side denylist has ever read.
 *
 * ⭐ THIS PAGE IS STATIC. It was a dynamic server component (`cache: "no-store"`) purely so it
 * could fetch the featured pick and the latest blog post at request time. The blog fetch is gone
 * with the demotion, and the pick moved into a client component so it is both mockable in
 * Playwright and no longer a reason to re-render the whole marketing page per visit. Nothing on
 * the page above the pick depends on a network call, which is also what guarantees the AC that a
 * failed read can never produce a blank hero.
 */

export const metadata = {
  title: "Credence Sports — honest sports analytics",
  description: HERO.subhead,
  openGraph: {
    title: "Credence Sports — honest sports analytics",
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

        {/* ⭐ THE DUAL ENTRY. Both verticals get a card of equal weight — a `md:grid-cols-2` and
            not a primary/secondary split, because the whole defect being fixed is a home page
            that read as one product. */}
        <div className="mt-12 grid gap-4 md:grid-cols-2">
          {VERTICALS.map((v) => (
            <div
              key={v.key}
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
                    statistic. NF-TR1's rule: a marketing surface LINKS to the record, it never
                    quotes its number. `needsAccount` is what keeps the MLB one from being a small
                    lie — `/performance` is behind the auth guard, and sending a stranger from a
                    trust link to a login wall is the one surprise a trust link cannot afford. */}
                <Link
                  href={v.trust.href}
                  className="inline-flex items-center gap-1.5 text-sm text-gray-400 underline-offset-4 transition-colors hover:text-[#10b981] hover:underline"
                >
                  {v.trust.label}
                  {v.trust.needsAccount ? (
                    <Lock className="h-3 w-3 text-gray-600" />
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

function PrinciplesSection() {
  return (
    <section className="border-t border-[#262626] py-16 md:py-20">
      <div className="mx-auto max-w-5xl px-4">
        <h2 className="text-balance text-center text-2xl font-bold text-white md:text-3xl">
          The same standard on both products
        </h2>
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

/** The fantasy click-driver: ADP as CONTENT, never as a boast (NF-TR1's `DISAGREEMENT_HOOK`).
 *  "Where we differ from the crowd and why" is a reason to click and stays true whichever side of
 *  the gap we are on; "we rank better than consensus" is a claim, and a small one whose own
 *  interval includes zero. */
function FantasyHookSection() {
  return (
    <section className="border-t border-[#262626] py-14 md:py-16">
      <div className="mx-auto max-w-3xl px-4">
        <div className="rounded-xl border border-[#262626] bg-[#141414] p-6 md:p-8">
          <p className="text-xs font-semibold uppercase tracking-widest text-[#10b981]">
            NFL Fantasy
          </p>
          <p className="mt-3 text-pretty text-base leading-relaxed text-gray-300 md:text-lg">
            {DISAGREEMENT_HOOK}
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2">
            <Button
              asChild
              variant="outline"
              className="border-[#262626] bg-transparent text-gray-200 hover:bg-[#1a1a1a] hover:text-white"
            >
              <Link href="/fantasy/rankings">
                Open the free rankings
                <ArrowRight className="ml-1.5 h-4 w-4" />
              </Link>
            </Button>
            <Link
              href={TRACK_RECORD_TRUST_LINK.href}
              className="text-sm text-gray-400 underline-offset-4 transition-colors hover:text-[#10b981] hover:underline"
            >
              {TRACK_RECORD_TRUST_LINK.label} &rarr;
            </Link>
          </div>
          <p className="mt-4 text-xs leading-relaxed text-gray-600">
            {TRACK_RECORD_TRUST_LINK.blurb}
          </p>
        </div>
      </div>
    </section>
  )
}

function SeasonRoadmapSection() {
  return (
    <section className="border-t border-[#262626] py-16 md:py-20">
      <div className="mx-auto max-w-3xl px-4">
        <h2 className="text-balance text-2xl font-bold text-white md:text-3xl">
          What is live, and what is next
        </h2>

        <ul className="mt-8 divide-y divide-[#262626] border-y border-[#262626]">
          {SEASON_ROADMAP.map((row) => (
            <li
              key={`${row.sport}-${row.what}`}
              className="flex flex-wrap items-center gap-x-4 gap-y-1 py-4"
            >
              <span
                className={`w-14 shrink-0 text-xs font-bold uppercase tracking-wider ${
                  row.live ? "text-[#10b981]" : "text-gray-600"
                }`}
              >
                {row.sport}
              </span>
              <span
                className={`flex-1 text-sm ${row.live ? "text-gray-200" : "text-gray-500"}`}
              >
                {row.what}
              </span>
              {/* ⛔ A not-yet-live row is TEXT, never a link. A "coming soon" CTA into a route
                  that does not exist is E9.56c's dead `/pricing` wearing a friendlier label. */}
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

function HonestySection() {
  return (
    <section className="border-t border-[#262626] py-12 md:py-16">
      <div className="mx-auto max-w-2xl px-4">
        <div className="rounded-xl border border-[#262626] bg-[#141414] p-8 md:p-10">
          <p className="text-pretty text-base leading-relaxed text-gray-300 md:text-lg">
            {HONESTY_STATEMENT}
          </p>
        </div>
      </div>
    </section>
  )
}

/** The blog, demoted (operator decision 3, 2026-08-07). It stays a real content surface — the
 *  GROWTH-100 engine keeps publishing to it — it just no longer competes with the product for
 *  home-page attention, so it is one secondary line here plus the footer, and it is out of the
 *  primary nav entirely. ⭐ It is a STATIC link rather than the previous request-time fetch of the
 *  latest post: rendering the post's own title made it a headline, which is the promotion this
 *  decision reverses, and it was also the last thing forcing this page to be dynamic. */
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
        {/* The live element, and the reason to come back tomorrow. It renders `id="today"`, which
            is the MLB card's own CTA target (`VERTICALS[betting].cta.href`). That pairing is two
            string literals in two files, so it is pinned by navigation instead of by types:
            `home-positioning.spec.ts` clicks the CTA and asserts this section is what it reaches. */}
        <PickOfTheDay />
        <FantasyHookSection />
        <PrinciplesSection />
        <SeasonRoadmapSection />
        <HonestySection />
        <LandingFaqSection />
        <SecondaryLinks />
        <FooterCta />
      </main>
    </div>
  )
}
