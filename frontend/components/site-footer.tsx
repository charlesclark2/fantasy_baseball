import Link from "next/link"

import { PlatformAttributionFooterSlot } from "@/components/fantasy/platform-attribution"

/**
 * E9.60 — the footer, restructured to spec §23: Products / Credence / Legal, fantasy-first.
 *
 * ══ WHAT CHANGED AND WHY ═══════════════════════════════════════════════════════════════════════
 *
 * It was a single flat row of six links. It renders on EVERY page (`app/layout.tsx`), so it is the
 * site's one constant navigation surface — and it carried FAQ but not About, and not the track
 * record, so the two pages E9.60 rewrites were reachable from each other in one direction only and
 * the central trust asset was absent entirely.
 *
 * ⛔ A NOT-YET-LIVE PRODUCT IS TEXT, NEVER A LINK. NFL betting intelligence is listed because a
 * visitor deciding whether to subscribe should see where this is going — but it renders as a muted
 * row under a "Coming this season" sub-heading and with NO anchor. This is the same rule the home
 * page's roadmap follows (`live: false` rows carry no `<Link>`), and it exists because E9.56c
 * shipped a primary CTA pointing at `/pricing`, a route that has never existed, and killed the buy
 * path for as long as the free pages were open.
 *
 * ⭐ AND ITS COROLLARY, WHICH NCAAF-P3.9 IS THE FIRST TO NEED: a product that GOES LIVE must stop
 * being text in the same change. `/ncaaf/games` shipped at P3.2 and this column went on saying
 * "Coming this season" about it — the rule above is what keeps an unbuilt product from being
 * oversold, and leaving a live one under it is the identical defect facing the other way, on the
 * one surface that renders on every page in the product.
 *
 * ⚠️ THE LINK ARRAYS STAY LITERAL, and that is deliberate rather than lazy. Two existing guards read
 * this file as SOURCE and a data-driven list would silently fall out of both:
 * `test_e9_46_home_copy.py::test_the_blog_is_still_reachable` asserts `href: "/blog"` is here (the
 * half that makes the blog's demotion from the nav a demotion rather than a deletion), and
 * `test_e9_56c_cta_routes.py` scans `.tsx` files for literal `href="/…"` to catch a link pointing at
 * a route with no `page.tsx`. Footer links are chrome, not claims, so they gain nothing from living
 * in the screened copy module and would lose two guards by moving.
 */

/** ⭐ FANTASY FIRST, matching the home page's `VERTICALS`, About's `ABOUT_PRODUCTS`, the signed-out
 *  bar's `SIGNED_OUT_NAV` and the signed-in `SPORTS` order. One product order, everywhere. */
const PRODUCTS = [
  { label: "Fantasy Football", href: "/fantasy/rankings" },
  // ⭐ NCAAF-P3.9 — PROMOTED OUT OF `COMING` (below), which is the whole point of the move: the
  // module header's rule is "a not-yet-live product is TEXT, never a link", and the corollary
  // nobody had had to apply yet is that a product that GOES live must stop being text in the same
  // change. `/ncaaf/games` has been live since P3.2 while this column still said "Coming this
  // season" — a footer that renders on every page telling every visitor the opposite of the truth.
  //
  // ⭐ It leads MLB because it is the FREE one: no account, no subscription (E9.45), so it is the
  // only betting row here a signed-out reader can actually open. MLB's `/#today` is an anchor into
  // the home page for exactly that reason.
  { label: "NCAAF Betting Intelligence", href: "/ncaaf/games" },
  { label: "MLB Betting Intelligence", href: "/#today" },
] as const

/** ⛔ NO `href` FIELD AT ALL — not an empty string, not a `#`. The type simply cannot express a
 *  destination for these, so a future edit cannot accidentally make one clickable.
 *
 *  ⭐ THESE SIT UNDER A SHARED "Coming this season" SUB-HEADING rather than each carrying its own
 *  chip, and that is a BUG FIX, not a restyle (operator report, 2026-08-09). Each row used to be
 *  `label + <chip>` in a `flex-wrap` — and the footer's Products column is roughly 250px at `md`,
 *  which fits "NFL Betting Intelligence" beside its chip but NOT "NCAAF Betting Intelligence". So
 *  one row wrapped its chip onto a second line and the other did not, and the ragged result read
 *  as broken layout.
 *
 *  ⛔ The tempting patches are both worse: `whitespace-nowrap` makes the row overflow the column
 *  instead of wrapping, and always-stacking the chip doubles the height of every row to fix one.
 *  Hoisting the label to a sub-heading makes the overflow IMPOSSIBLE (there is nothing beside the
 *  text to wrap), and it reads better — a labelled group is clearer than a repeated chip. The
 *  "coming this season" string is still present exactly once, which is what
 *  `positioning-alignment.spec.ts` asserts. */
const COMING = [
  // ⚠️ NCAAF-P3.9 REMOVED THE NCAAF ROW — it is LIVE and now sits in `PRODUCTS` above. NFL betting
  // remains genuinely unbuilt, so the shared "Coming this season" sub-heading still has exactly one
  // member to head and still renders exactly once, which is what
  // `positioning-alignment.spec.ts` asserts.
  { label: "NFL Betting Intelligence" },
] as const

const CREDENCE = [
  { label: "About", href: "/about" },
  { label: "Track Record", href: "/fantasy/track-record" },
  { label: "FAQ", href: "/faq" },
  { label: "What's New", href: "/changelog" },
  { label: "Blog", href: "/blog" },
  { label: "Contact", href: "/contact" },
] as const

const LEGAL = [
  { label: "Privacy Policy", href: "/privacy" },
  { label: "Terms of Service", href: "/terms" },
] as const

export function SiteFooter() {
  return (
    <footer className="border-t border-[#262626] bg-[#0a0a0a]">
      <div className="mx-auto max-w-6xl px-4 py-10">
        <div className="grid gap-8 sm:grid-cols-2 md:grid-cols-4">
          {/* Wordmark */}
          <div>
            <span className="text-sm font-bold">
              <span className="text-[#10b981]">Credence</span>
              <span className="text-white"> Sports</span>
            </span>
            <p className="mt-2 text-xs leading-relaxed text-gray-600">
              Analysis published with the uncertainty attached.
            </p>
          </div>

          <FooterColumn heading="Products">
            {PRODUCTS.map(({ label, href }) => (
              <FooterLink key={label} href={href} label={label} />
            ))}
            {/* The sub-heading carries the status once; the rows below are plain text, never
                links — see the note on COMING. `aria-hidden` is deliberately NOT used: this is
                real information for a screen reader too. */}
            <li className="pt-2">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-600">
                Coming this season
              </p>
            </li>
            {COMING.map(({ label }) => (
              // Text, not a link — see the module header.
              <li key={label}>
                <span className="text-xs text-gray-600">{label}</span>
              </li>
            ))}
          </FooterColumn>

          <FooterColumn heading="Credence">
            {CREDENCE.map(({ label, href }) => (
              <FooterLink key={label} href={href} label={label} />
            ))}
          </FooterColumn>

          <FooterColumn heading="Legal">
            {LEGAL.map(({ label, href }) => (
              <FooterLink key={label} href={href} label={label} />
            ))}
          </FooterColumn>
        </div>

        <div className="mt-8 border-t border-[#262626] pt-6">
          <span className="text-xs text-gray-600">&copy; 2026 Penumbra Partners</span>
          {/* 🚩 THE PLATFORM ATTRIBUTION, WHICH THE AGREEMENT PUTS HERE SPECIFICALLY.
              Yahoo's Cover Page: "attribution must appear in the FOOTER OF EACH PAGE where Yahoo
              Fantasy Information is displayed and must include a hyperlink to an official Yahoo
              Fantasy webpage." A page-level component cannot render into this footer — it is a
              SIBLING of `{children}` in the root layout — so the surfaces register what they are
              displaying and this slot draws it. Renders NOTHING on a page showing no such data,
              which is the other half of the requirement: crediting Yahoo for data Yahoo did not
              supply is its own false statement. See `platform-attribution.tsx`. */}
          <PlatformAttributionFooterSlot className="mt-2" />
        </div>
      </div>
    </footer>
  )
}

function FooterColumn({ heading, children }: { heading: string; children: React.ReactNode }) {
  return (
    <nav aria-label={heading}>
      <p className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-gray-500">
        {heading}
      </p>
      <ul className="space-y-2">{children}</ul>
    </nav>
  )
}

function FooterLink({ href, label }: { href: string; label: string }) {
  return (
    <li>
      <Link
        href={href}
        className="text-xs text-gray-400 transition-colors hover:text-white"
      >
        {label}
      </Link>
    </li>
  )
}
