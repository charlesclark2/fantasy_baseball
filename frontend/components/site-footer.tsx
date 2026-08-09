import Link from "next/link"

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
 * ⛔ A NOT-YET-LIVE PRODUCT IS TEXT, NEVER A LINK. NFL and NCAAF betting intelligence are listed
 * because a visitor deciding whether to subscribe should see where this is going — but they render
 * as a muted row with a "Coming this season" tag and NO anchor. This is the same rule the home
 * page's roadmap follows (`live: false` rows carry no `<Link>`), and it exists because E9.56c
 * shipped a primary CTA pointing at `/pricing`, a route that has never existed, and killed the buy
 * path for as long as the free pages were open.
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
  { label: "MLB Betting Intelligence", href: "/#today" },
] as const

/** ⛔ NO `href` FIELD AT ALL — not an empty string, not a `#`. The type simply cannot express a
 *  destination for these, so a future edit cannot accidentally make one clickable. */
const COMING = [
  { label: "NFL Betting Intelligence" },
  { label: "NCAAF Betting Intelligence" },
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
            {COMING.map(({ label }) => (
              // Text, not a link — see the module header.
              <li key={label} className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="text-xs text-gray-600">{label}</span>
                <span className="rounded border border-[#262626] px-1.5 py-0.5 text-[10px] text-gray-600">
                  Coming this season
                </span>
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
