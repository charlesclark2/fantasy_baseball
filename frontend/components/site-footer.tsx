import Link from "next/link"

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
          {[
            { label: "FAQ", href: "/faq" },
            { label: "Blog", href: "/blog" },
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
