import Link from "next/link"
import { Nav } from "@/components/nav"
import { SIGNUP_HREF } from "@/lib/access"
import {
  ABOUT_ACCOUNTABILITY,
  ABOUT_AUDIENCE,
  ABOUT_BELIEFS,
  ABOUT_CTA,
  ABOUT_EVALUATION,
  ABOUT_HERO,
  ABOUT_NOT,
  ABOUT_PRODUCTS,
  ABOUT_PULL_QUOTE,
  ABOUT_RANGES,
  ABOUT_WHY,
  type ProductBlock,
} from "@/lib/positioning-copy"

/**
 * E9.60 — the About page, brought into alignment with the live home-page positioning.
 *
 * ══ WHAT WAS WRONG ═════════════════════════════════════════════════════════════════════════════
 *
 * This page still described a one-sport company. Its H1 was "An honest maybe beats a confident
 * guess", its subhead read "We forecast baseball the way the evidence supports", and its "who it's
 * for" paragraph addressed a Fangraphs reader — on a site whose home page leads with an NFL fantasy
 * product. A visitor who clicked About off the home page met a contradiction on the second click.
 *
 * ══ THE SHAPE ══════════════════════════════════════════════════════════════════════════════════
 *
 *   Hero              "Better sports decisions start with knowing what you don't know."
 *        ↓
 *   Why Credence exists                    ← the questions a bare number leaves unanswered
 *        ↓
 *   TWO PRODUCTS, ONE STANDARD             ← fantasy first, each split LIVE vs COMING
 *        ↓
 *   What we believe (five principles)
 *        ↓
 *   Ranges · How we judge ourselves · Wins and losses both belong on the page
 *        ↓
 *   Who it is for · What Credence is not · CTA
 *
 * ⭐ FANTASY FIRST, matching the home page's `VERTICALS` and the nav. One product order everywhere.
 *
 * ⛔ THE CLAIM RULE. `best_alpha = 0`. Every claim-bearing sentence lives in
 * `lib/positioning-copy.ts` and is screened by `betting_ml/tests/test_e9_60_positioning_copy.py`;
 * the RENDERED page is scanned again by `e2e/specs/positioning-alignment.spec.ts`, which is the only
 * instrument that can see a heading or a CTA label.
 *
 * ⭐ THIS PAGE IS STATIC — no read at request time, so it never joins G100-D1's three registries.
 */

export const metadata = {
  title: "About — Credence Sports",
  description: ABOUT_HERO.subhead,
}

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Nav />

      <main className="flex-1 mx-auto w-full max-w-3xl px-6 py-16">
        {/* ══ Hero ══ */}
        <p className="text-xs uppercase tracking-widest text-muted-foreground mb-10">
          {ABOUT_HERO.eyebrow}
        </p>

        <div className="mb-16">
          <h1 className="text-4xl sm:text-5xl font-bold text-white leading-tight tracking-tight mb-5">
            {ABOUT_HERO.headline}
          </h1>
          <p className="text-base sm:text-lg text-gray-400 leading-relaxed">
            {ABOUT_HERO.subhead}
          </p>
        </div>

        {/* ══ Why Credence exists ══ */}
        <Section heading={ABOUT_WHY.heading}>
          {ABOUT_WHY.paragraphs.map((p) => (
            <p key={p} className="text-sm sm:text-base text-gray-400 leading-relaxed mb-4">
              {p}
            </p>
          ))}
          <PullQuote>{ABOUT_WHY.pullQuote}</PullQuote>
        </Section>

        {/* ══ Two products, one standard ══
            The LIVE/COMING split is the honest half of this section and is rendered as two visually
            distinct groups — spec §7: "These should be visually separated from the live
            capabilities." A single styled list would put un-shipped weekly tools a glance away from
            reading as available. */}
        <Section heading="Two products, one standard">
          <div className="space-y-10">
            {ABOUT_PRODUCTS.map((p) => (
              <ProductSection key={p.key} product={p} />
            ))}
          </div>
        </Section>

        {/* ══ What we believe ══ */}
        <Section heading="What we believe">
          <div className="divide-y divide-[#262626]">
            {ABOUT_BELIEFS.map((b) => (
              <div key={b.index} className="py-5 flex gap-5 sm:gap-8 items-start">
                <span className="text-xs tabular-nums text-muted-foreground w-5 mt-0.5 shrink-0 select-none">
                  {b.index}
                </span>
                <div>
                  <p className="text-sm font-semibold text-white mb-1">{b.title}</p>
                  <p className="text-sm text-gray-400 leading-relaxed">{b.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </Section>

        {/* ══ The retained pull quote — demoted from H1, kept in the page (spec §9) ══ */}
        <div className="mb-16 border-l-2 border-[#10b981] pl-6">
          <p className="font-serif text-lg sm:text-xl text-gray-200 leading-relaxed italic">
            {ABOUT_PULL_QUOTE.quote}
          </p>
          <p className="mt-3 font-serif text-base text-gray-400 leading-relaxed italic">
            {ABOUT_PULL_QUOTE.support}
          </p>
        </div>

        {/* ══ Ranges ══ */}
        <Section heading={ABOUT_RANGES.heading}>
          <p className="text-sm sm:text-base text-gray-400 leading-relaxed mb-5">
            {ABOUT_RANGES.body}
          </p>
          <p className="text-xs uppercase tracking-widest text-muted-foreground mb-3">
            {ABOUT_RANGES.appearsInHeading}
          </p>
          <ul className="space-y-1.5">
            {ABOUT_RANGES.appearsIn.map((item) => (
              <li key={item} className="flex gap-2.5 text-sm text-gray-400 leading-relaxed">
                <span className="text-[#10b981] shrink-0">—</span>
                {item}
              </li>
            ))}
          </ul>
        </Section>

        {/* ══ How we judge ourselves ══ */}
        <Section heading={ABOUT_EVALUATION.heading}>
          {ABOUT_EVALUATION.paragraphs.map((p) => (
            <p key={p} className="text-sm sm:text-base text-gray-400 leading-relaxed mb-4">
              {p}
            </p>
          ))}
          <PullQuote>{ABOUT_EVALUATION.pullQuote}</PullQuote>
        </Section>

        {/* ══ Public accountability ══
            ⭐ THE LINK IS THE POINT OF THE SECTION. It talked about a record without offering a
            route to it, which is the shape NF-TR1 exists to prevent — a marketing surface LINKS to
            the evidence rather than quoting its number, and a section arguing for inspectability
            that cannot be inspected argues against itself. The literal href also keeps this inside
            `test_e9_56c_cta_routes.py`'s static scan.
            ⚠️ It points at the FANTASY record, which is genuinely open to anyone; the MLB record is
            behind the paid guard and is named in the prose as the members' scorecard rather than
            linked, so a stranger is never sent into a login wall from here. */}
        <Section heading={ABOUT_ACCOUNTABILITY.heading}>
          {ABOUT_ACCOUNTABILITY.paragraphs.map((p) => (
            <p key={p} className="text-sm sm:text-base text-gray-400 leading-relaxed mb-4">
              {p}
            </p>
          ))}
          <Link
            href="/fantasy/track-record"
            className="mt-2 inline-flex text-sm text-[#10b981] hover:underline"
          >
            See the fantasy track record →
          </Link>
        </Section>

        {/* ══ Who it's for ══ */}
        <Section heading={ABOUT_AUDIENCE.heading}>
          {ABOUT_AUDIENCE.paragraphs.map((p) => (
            <p key={p} className="text-sm sm:text-base text-gray-400 leading-relaxed mb-4">
              {p}
            </p>
          ))}
        </Section>

        {/* ══ What Credence is not ══ */}
        <Section heading={ABOUT_NOT.heading}>
          <ul className="space-y-2.5 mb-6">
            {ABOUT_NOT.items.map((item) => (
              <li key={item} className="flex gap-2.5 text-sm text-gray-400 leading-relaxed">
                <span className="text-gray-600 shrink-0">—</span>
                {item}
              </li>
            ))}
          </ul>
          <PullQuote>{ABOUT_NOT.closer}</PullQuote>
        </Section>

        {/* ══ Closing CTA ══
            ⛔ Every href here serves an anonymous visitor — see the note on `ABOUT_CTA`. */}
        <div className="border-t border-[#262626] pt-10">
          <h2 className="text-xl font-bold text-white mb-3">{ABOUT_CTA.heading}</h2>
          <p className="text-sm text-gray-400 leading-relaxed mb-6">{ABOUT_CTA.detail}</p>
          <div className="flex flex-wrap gap-3">
            {/* ⭐ THE SIGNUP AFFORDANCE, RESTORED AND WRITTEN OUT RATHER THAN DATA-DRIVEN.
                The E9.60 rewrite dropped this page's "Create an account" button, which was a real
                regression rather than a test artifact: About is a top-of-funnel page and that was
                its only conversion affordance. `test_e9_58_public_signup.py` caught it by name —
                About is one of the five surfaces E9.56c enumerated as having carried the dead
                `mailto:` — and it stays a literal `SIGNUP_HREF` reference here so that guard keeps
                covering this page. */}
            <Link
              href={SIGNUP_HREF}
              className="inline-flex items-center rounded-md bg-[#10b981] px-4 py-2 text-sm font-semibold text-[#0a0a0a] hover:bg-[#059669] transition-colors"
            >
              Create a free account
            </Link>
            {ABOUT_CTA.buttons.map((b) => (
              <Link
                key={b.href}
                href={b.href}
                className={
                  b.primary
                    ? "inline-flex items-center rounded-md border border-[#10b981]/40 px-4 py-2 text-sm font-semibold text-[#10b981] hover:border-[#10b981] transition-colors"
                    : "inline-flex items-center rounded-md border border-[#262626] px-4 py-2 text-sm text-gray-300 hover:text-white hover:border-[#404040] transition-colors"
                }
              >
                {b.label}
              </Link>
            ))}
          </div>
          <p className="mt-8 text-xs text-muted-foreground">{ABOUT_CTA.footnote}</p>
        </div>
      </main>
    </div>
  )
}

function Section({ heading, children }: { heading: string; children: React.ReactNode }) {
  return (
    <section className="mb-16">
      <h2 className="text-xl font-bold text-white mb-4">{heading}</h2>
      {children}
    </section>
  )
}

function PullQuote({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-5 border-l-2 border-[#10b981] pl-5 font-serif text-base sm:text-lg text-gray-200 leading-relaxed italic">
      {children}
    </p>
  )
}

/**
 * One product, split into what ships today and what does not.
 *
 * ⭐ THE TWO GROUPS ARE STYLED APART ON PURPOSE and it is the load-bearing detail of this page.
 * The live list carries the emerald marker the rest of the site uses for shipped things; the coming
 * list is muted, dashed, and labelled. `data-product` / `data-capability` are TEST HANDLES — the
 * e2e spec asserts that no un-shipped capability sits in a live group, and it cannot do that from
 * text alone because both lists render the same words in different places.
 */
function ProductSection({ product }: { product: ProductBlock }) {
  return (
    <div data-product={product.key}>
      <h3 className="text-base font-semibold text-white mb-2">{product.label}</h3>
      <p className="text-sm text-gray-400 leading-relaxed mb-5">{product.lede}</p>

      <div className="grid gap-5 sm:grid-cols-2">
        {/* Live */}
        <div data-capability="live" className="rounded-lg border border-[#10b981]/25 bg-[#10b981]/[0.04] p-4">
          <p className="text-[11px] font-bold uppercase tracking-wider text-[#10b981] mb-2.5">
            {product.live.heading}
          </p>
          <ul className="space-y-1.5 mb-3">
            {product.live.items.map((i) => (
              <li key={i} className="text-sm text-gray-300 leading-relaxed">
                {i}
              </li>
            ))}
          </ul>
          <p className="text-xs text-gray-500 leading-relaxed">{product.live.note}</p>
        </div>

        {/* Coming — never a link, and never styled as available (the home page's `live: false`
            roadmap rule, applied here). */}
        <div
          data-capability="coming"
          className="rounded-lg border border-dashed border-[#262626] p-4"
        >
          <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500 mb-2.5">
            {product.coming.heading}
          </p>
          <ul className="space-y-1.5 mb-3">
            {product.coming.items.map((i) => (
              <li key={i} className="text-sm text-gray-500 leading-relaxed">
                {i}
              </li>
            ))}
          </ul>
          <p className="text-xs text-gray-600 leading-relaxed">{product.coming.note}</p>
        </div>
      </div>
    </div>
  )
}
