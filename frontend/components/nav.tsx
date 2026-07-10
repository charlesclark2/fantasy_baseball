"use client"

import { useState } from "react"
import Image from "next/image"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { LogOut, Settings, Menu, X, ChevronDown } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/lib/auth-context"
import changelog from "@/data/changelog.json"

type ActiveLink =
  | "dashboard"
  | "ev-tracker"
  | "performance"
  | "settings"
  | "bet-log"
  | "admin"
  | "blog"
  | "changelog"
  | "teams"
  | "players"
  | "props"
  | "parlay"
  | null

const latestWeek = changelog[0]?.week
const isChangelogRecent = latestWeek
  ? (Date.now() - new Date(latestWeek + "T00:00:00").getTime()) /
      (1000 * 60 * 60 * 24) <=
    7
  : false

interface NavProps {
  activeLink?: ActiveLink
  authenticated?: boolean
  userEmail?: string | null
}

// Personal betting workflow — collapsed into a "Betting" dropdown to keep the sub-nav uncrowded.
// Props = the daily model-projection surface (transparency, not a bet rec).
const BETTING_ITEMS = [
  { label: "Dashboard", href: "/dashboard", key: "dashboard" },
  { label: "EV Tracker", href: "/ev-tracker", key: "ev-tracker" },
  { label: "Props", href: "/props", key: "props" },
  { label: "Parlay Calculator", href: "/parlay", key: "parlay" },
] as const

const MAIN_NAV_ITEMS = [
  { label: "Performance", href: "/performance", key: "performance" },
  { label: "Bet Log", href: "/bet-log", key: "bet-log" },
] as const

const RESEARCH_ITEMS = [
  { label: "Teams", href: "/teams", key: "teams" },
  { label: "Players", href: "/players", key: "players" },
] as const

const ADMIN_ITEMS = [
  { label: "Admin Dashboard", href: "/admin", key: "admin" },
  { label: "Blog Editor", href: "/admin/blog", key: "blog" },
] as const

export function Nav({
  activeLink = null,
  authenticated = false,
  userEmail,
}: NavProps) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const { accessToken, isAdmin, signOut } = useAuth()
  const router = useRouter()
  const isSignedIn = !!accessToken
  const showSubNav = authenticated || isSignedIn

  const flatLinkClass = (key: string) =>
    activeLink === key
      ? "border-b-2 border-[#10b981] pb-2.5 text-sm text-white font-medium transition-colors whitespace-nowrap"
      : "border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors whitespace-nowrap"

  const isBettingActive = BETTING_ITEMS.some((i) => i.key === activeLink)
  const isResearchActive = RESEARCH_ITEMS.some((i) => i.key === activeLink)
  const isAdminActive = ADMIN_ITEMS.some((i) => i.key === activeLink)

  return (
    <nav className="sticky top-0 z-50 border-b border-[#262626] bg-[#0a0a0a]/90 backdrop-blur-md">
      {/* Top bar */}
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        <Link href="/">
          <Image
            src="/brand/logo-full.svg"
            alt="Credence Sports"
            width={240}
            height={48}
            className="h-12 w-auto"
            priority
          />
        </Link>

        <div className="flex items-center gap-3">
          {/* About + Blog — desktop only */}
          <Link
            href="/about"
            className="hidden text-xs text-gray-500 hover:text-gray-300 transition-colors sm:block"
          >
            About
          </Link>
          <Link
            href="/blog"
            className="hidden text-xs text-gray-500 hover:text-gray-300 transition-colors sm:block"
          >
            Blog
          </Link>

          {/* User actions — desktop only */}
          {authenticated ? (
            <div className="hidden sm:flex items-center gap-3">
              <span className="text-xs text-gray-500">{userEmail ?? "—"}</span>
              <Button
                variant="ghost"
                size="sm"
                asChild
                className="text-gray-400 hover:text-white hover:bg-[#141414]"
              >
                <Link href="/settings">
                  <Settings className="h-3.5 w-3.5" />
                  <span className="sr-only">Settings</span>
                </Link>
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-gray-400 hover:text-white hover:bg-[#141414]"
                onClick={() => {
                  signOut()
                  router.push("/login")
                }}
              >
                <LogOut className="mr-1.5 h-3.5 w-3.5" />
                Sign Out
              </Button>
            </div>
          ) : isSignedIn ? (
            <Button
              size="sm"
              asChild
              className="hidden sm:flex bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
            >
              <Link href="/dashboard">Dashboard</Link>
            </Button>
          ) : (
            <div className="hidden sm:flex items-center gap-3">
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
                <a href="mailto:charlie@credencesports.com?subject=Beta%20Access%20Request">
                  Request Access
                </a>
              </Button>
            </div>
          )}

          {/* Hamburger — mobile only, shown when signed in */}
          {showSubNav && (
            <button
              className="flex items-center justify-center rounded p-1.5 text-gray-400 hover:text-white hover:bg-[#141414] transition-colors sm:hidden"
              onClick={() => setMobileOpen(!mobileOpen)}
              aria-label="Toggle menu"
            >
              {mobileOpen ? (
                <X className="h-5 w-5" />
              ) : (
                <Menu className="h-5 w-5" />
              )}
            </button>
          )}
        </div>
      </div>

      {/* Desktop sub-nav */}
      {showSubNav && (
        <div className="mx-auto hidden max-w-6xl items-center gap-6 px-4 pb-0 sm:flex">
          {/* Betting dropdown */}
          <div className="group relative">
            <button
              className={`flex items-center gap-1 pb-2.5 text-sm transition-colors whitespace-nowrap ${
                isBettingActive
                  ? "border-b-2 border-[#10b981] font-medium text-white"
                  : "border-b-2 border-transparent text-gray-500 hover:text-gray-300"
              }`}
            >
              Betting
              <ChevronDown className="h-3 w-3" />
            </button>
            <div className="absolute left-0 top-full z-50 hidden w-36 rounded-md border border-[#262626] bg-[#0f0f0f] py-1 shadow-xl group-hover:block">
              {BETTING_ITEMS.map(({ label, href, key }) => (
                <Link
                  key={key}
                  href={href}
                  className={`block px-3 py-2 text-sm transition-colors ${
                    activeLink === key
                      ? "text-white bg-[#1a1a1a]"
                      : "text-gray-400 hover:text-white hover:bg-[#1a1a1a]"
                  }`}
                >
                  {label}
                </Link>
              ))}
            </div>
          </div>

          {MAIN_NAV_ITEMS.map(({ label, href, key }) => (
            <Link key={key} href={href} className={flatLinkClass(key)}>
              {label}
            </Link>
          ))}

          {/* Research dropdown */}
          <div className="group relative">
            <button
              className={`flex items-center gap-1 pb-2.5 text-sm transition-colors whitespace-nowrap ${
                isResearchActive
                  ? "border-b-2 border-[#10b981] font-medium text-white"
                  : "border-b-2 border-transparent text-gray-500 hover:text-gray-300"
              }`}
            >
              Research
              <ChevronDown className="h-3 w-3" />
            </button>
            <div className="absolute left-0 top-full z-50 hidden w-36 rounded-md border border-[#262626] bg-[#0f0f0f] py-1 shadow-xl group-hover:block">
              {RESEARCH_ITEMS.map(({ label, href, key }) => (
                <Link
                  key={key}
                  href={href}
                  className={`block px-3 py-2 text-sm transition-colors ${
                    activeLink === key
                      ? "text-white bg-[#1a1a1a]"
                      : "text-gray-400 hover:text-white hover:bg-[#1a1a1a]"
                  }`}
                >
                  {label}
                </Link>
              ))}
            </div>
          </div>

          {/* What's New */}
          <Link
            href="/changelog"
            className={
              activeLink === "changelog"
                ? "flex items-center gap-1.5 border-b-2 border-[#10b981] pb-2.5 text-sm font-medium text-white transition-colors whitespace-nowrap"
                : "flex items-center gap-1.5 border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors whitespace-nowrap"
            }
          >
            What&apos;s New
            {isChangelogRecent && (
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
            )}
          </Link>

          {/* Admin dropdown */}
          {isAdmin && (
            <div className="group relative">
              <button
                className={`flex items-center gap-1 pb-2.5 text-sm transition-colors whitespace-nowrap ${
                  isAdminActive
                    ? "border-b-2 border-[#10b981] font-medium text-white"
                    : "border-b-2 border-transparent text-gray-500 hover:text-gray-300"
                }`}
              >
                Admin
                <ChevronDown className="h-3 w-3" />
              </button>
              <div className="absolute left-0 top-full z-50 hidden w-40 rounded-md border border-[#262626] bg-[#0f0f0f] py-1 shadow-xl group-hover:block">
                {ADMIN_ITEMS.map(({ label, href, key }) => (
                  <Link
                    key={key}
                    href={href}
                    className={`block px-3 py-2 text-sm transition-colors ${
                      activeLink === key
                        ? "text-white bg-[#1a1a1a]"
                        : "text-gray-400 hover:text-white hover:bg-[#1a1a1a]"
                    }`}
                  >
                    {label}
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Mobile slide-down menu */}
      {showSubNav && mobileOpen && (
        <div className="border-t border-[#262626] bg-[#0a0a0a] px-4 py-3 sm:hidden">
          <div className="flex flex-col gap-0.5">
            <span className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-600">
              Betting
            </span>
            {BETTING_ITEMS.map(({ label, href, key }) => (
              <Link
                key={key}
                href={href}
                onClick={() => setMobileOpen(false)}
                className={`rounded-md px-3 py-2.5 text-sm font-medium transition-colors ${
                  activeLink === key
                    ? "bg-[#1a1a1a] text-white"
                    : "text-gray-400 hover:bg-[#141414] hover:text-white"
                }`}
              >
                {label}
              </Link>
            ))}

            <div className="my-2 border-t border-[#262626]" />
            {MAIN_NAV_ITEMS.map(({ label, href, key }) => (
              <Link
                key={key}
                href={href}
                onClick={() => setMobileOpen(false)}
                className={`rounded-md px-3 py-2.5 text-sm font-medium transition-colors ${
                  activeLink === key
                    ? "bg-[#1a1a1a] text-white"
                    : "text-gray-400 hover:bg-[#141414] hover:text-white"
                }`}
              >
                {label}
              </Link>
            ))}

            <div className="my-2 border-t border-[#262626]" />
            <span className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-600">
              Research
            </span>
            {RESEARCH_ITEMS.map(({ label, href, key }) => (
              <Link
                key={key}
                href={href}
                onClick={() => setMobileOpen(false)}
                className={`rounded-md px-3 py-2.5 text-sm font-medium transition-colors ${
                  activeLink === key
                    ? "bg-[#1a1a1a] text-white"
                    : "text-gray-400 hover:bg-[#141414] hover:text-white"
                }`}
              >
                {label}
              </Link>
            ))}

            <div className="my-2 border-t border-[#262626]" />
            <Link
              href="/changelog"
              onClick={() => setMobileOpen(false)}
              className={`flex items-center gap-2 rounded-md px-3 py-2.5 text-sm font-medium transition-colors ${
                activeLink === "changelog"
                  ? "bg-[#1a1a1a] text-white"
                  : "text-gray-400 hover:bg-[#141414] hover:text-white"
              }`}
            >
              What&apos;s New
              {isChangelogRecent && (
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              )}
            </Link>

            {isAdmin && (
              <>
                <div className="my-2 border-t border-[#262626]" />
                <span className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-600">
                  Admin
                </span>
                {ADMIN_ITEMS.map(({ label, href, key }) => (
                  <Link
                    key={key}
                    href={href}
                    onClick={() => setMobileOpen(false)}
                    className={`rounded-md px-3 py-2.5 text-sm font-medium transition-colors ${
                      activeLink === key
                        ? "bg-[#1a1a1a] text-white"
                        : "text-gray-400 hover:bg-[#141414] hover:text-white"
                    }`}
                  >
                    {label}
                  </Link>
                ))}
              </>
            )}

            <div className="my-2 border-t border-[#262626]" />
            {authenticated ? (
              <>
                {userEmail && (
                  <span className="px-3 py-1 text-xs text-gray-600">
                    {userEmail}
                  </span>
                )}
                <Link
                  href="/settings"
                  onClick={() => setMobileOpen(false)}
                  className="flex items-center gap-2 rounded-md px-3 py-2.5 text-sm text-gray-400 hover:bg-[#141414] hover:text-white transition-colors"
                >
                  <Settings className="h-4 w-4" />
                  Settings
                </Link>
                <button
                  onClick={() => {
                    signOut()
                    router.push("/login")
                    setMobileOpen(false)
                  }}
                  className="flex items-center gap-2 rounded-md px-3 py-2.5 text-left text-sm text-gray-400 hover:bg-[#141414] hover:text-white transition-colors"
                >
                  <LogOut className="h-4 w-4" />
                  Sign Out
                </button>
              </>
            ) : (
              <Link
                href="/login"
                onClick={() => setMobileOpen(false)}
                className="rounded-md px-3 py-2.5 text-sm text-gray-400 hover:bg-[#141414] hover:text-white transition-colors"
              >
                Sign In
              </Link>
            )}
          </div>
        </div>
      )}
    </nav>
  )
}
