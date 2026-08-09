import Link from "next/link"

/**
 * E9.60 — the link set moved to `lib/positioning-copy.ts` and gained About + Track Record.
 *
 * ⭐ SCOPED DELIBERATELY. Spec §23 proposes a three-column Products / Credence / Legal footer; that
 * belongs to the spec's own Scope B (§24, the information-architecture follow-on) and this story is
 * Scope A. What is fixed here is the DISCOVERABILITY half only: this footer renders on EVERY page
 * (`app/layout.tsx`) and carried FAQ but not About, so the two pages E9.60 rewrites were reachable
 * from each other in one direction only, and the track record — the site's central trust asset —
 * was absent entirely. The layout is untouched.
 */
export function SiteFooter() {
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
        <nav className="flex flex-wrap items-center justify-center gap-4">
          {/* ⚠️ KEPT AS A LITERAL ARRAY, and that is deliberate rather than lazy. Two existing
              guards read these as SOURCE, and a data-driven list would silently fall out of both:
              `test_e9_46_home_copy.py::test_the_blog_is_still_reachable` asserts `href: "/blog"` is
              here (the half that makes the blog's demotion a demotion rather than a deletion), and
              `test_e9_56c_cta_routes.py` scans `.tsx` files for literal `href="/…"` to catch a
              button pointing at a route that does not exist. E9.60 therefore ADDS to this array
              instead of moving it. */}
          {[
            { label: "About", href: "/about" },
            { label: "FAQ", href: "/faq" },
            { label: "Track Record", href: "/fantasy/track-record" },
            { label: "Blog", href: "/blog" },
            { label: "Changelog", href: "/changelog" },
            { label: "Privacy Policy", href: "/privacy" },
            { label: "Terms", href: "/terms" },
            { label: "Contact", href: "/contact" },
          ].map(({ label, href }) => (
            <Link
              key={label}
              href={href}
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
