"use client"

import { useEffect, useState } from "react"
import Image from "next/image"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { LogOut, Settings, Menu, X, ChevronDown, Lock } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/lib/auth-context"
import { SIGNUP_HREF } from "@/lib/access"
import { canAccess, canAccessFantasyBeta } from "@/lib/entitlements"
import { SPORTS, surfaceItems, publicNavItems, type NavItem, type SportNav, type SurfaceGroup } from "@/lib/nav-model"
import changelog from "@/data/changelog.json"

const latestWeek = changelog[0]?.week

// ⚠️ CLIENT-ONLY BY DESIGN — do NOT hoist this back to module scope.
// It used to be a module-level constant, which made it a hydration bug on every page in the app:
// most routes are STATICALLY PRERENDERED, so `Date.now()` on the server is frozen at BUILD time
// while the browser evaluates it live. Once a build ages past the 7-day boundary the two disagree
// and the "new" dot renders on one side only. (`new Date("YYYY-MM-DDT00:00:00")` has no timezone
// designator, so it is parsed in LOCAL time too — a second, independent server/client divergence.)
// Computing it after mount means the server and the hydration render always agree on "no dot", and
// the dot appears a tick later if it is genuinely recent.
function useChangelogRecent(): boolean {
  const [recent, setRecent] = useState(false)
  useEffect(() => {
    if (!latestWeek) return
    const days = (Date.now() - new Date(latestWeek + "T00:00:00").getTime()) / (1000 * 60 * 60 * 24)
    setRecent(days <= 7)
  }, [])
  return recent
}

interface NavProps {
  activeLink?: string | null
  authenticated?: boolean
  userEmail?: string | null
}

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
  const { accessToken, groups, isAdmin, signOut } = useAuth()
  const router = useRouter()
  const isSignedIn = !!accessToken
  const showSubNav = authenticated || isSignedIn

  const isAdminActive = ADMIN_ITEMS.some((i) => i.key === activeLink)
  const isChangelogRecent = useChangelogRecent()

  // A fantasy surface the caller isn't entitled to → visible but LOCKED (upsell).
  const isLocked = (g: SurfaceGroup) =>
    g.surface === "fantasy" && !canAccess("fantasy", groups)

  // An ITEM can require MORE than its surface (NF-C0b's league-settings editor is
  // admin + fantasy_comp only; E8.1's MLB prospect board is admin-only while it is in
  // development). Unlike a locked surface this is HIDDEN, not upsold — it is a staged
  // rollout, not something a subscriber can buy their way into.
  const visibleItems = (items: NavItem[]) =>
    items.filter((i) => {
      if (i.restrict === "fantasy_beta") return canAccessFantasyBeta(groups)
      if (i.restrict === "admin") return isAdmin
      return true
    })

  // 🐛 A surface whose items are ALL restricted away must not render at all. E8.1 added an
  // MLB→Fantasy surface whose only two items are admin-only, so for an entitled NON-admin
  // `isLocked` is false (they do have fantasy) while `visibleItems` is empty — which would draw
  // a bare "FANTASY" heading with nothing under it. An empty dropdown section reads as a broken
  // menu, so drop the whole group. A LOCKED group still renders: its upsell is the content.
  const visibleSurfaces = (sport: SportNav) =>
    sport.surfaces.filter(
      (g) => isLocked(g) || g.sections.some((s) => visibleItems(s.items).length > 0),
    )

  const itemClass = (key: string) =>
    `block px-3 py-2 text-sm transition-colors ${
      activeLink === key
        ? "text-white bg-[#1a1a1a]"
        : "text-gray-400 hover:text-white hover:bg-[#1a1a1a]"
    }`

  return (
    <nav className="sticky top-0 z-50 border-b border-[#262626] bg-[#0a0a0a]/90 backdrop-blur-md">
      {/* Top bar */}
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        {/* `shrink-0` so the wordmark can never be squeezed into the links beside it, and a
            smaller mark below `sm` — at h-12 the logo alone took a third of a 390px bar. */}
        <Link href="/" className="shrink-0">
          <Image
            src="/brand/logo-full.svg"
            alt="Credence Sports"
            width={240}
            height={48}
            className="h-9 w-auto sm:h-12"
            priority
          />
        </Link>

        <div className="flex items-center gap-2 sm:gap-3">
          {/* About — desktop only.
              ⛔ BLOG IS DELIBERATELY NOT HERE (E9.46, operator decision 3, 2026-08-07). It is a
              real content surface and the GROWTH-100 engine keeps publishing to it; it simply no
              longer competes with the two products for primary-nav attention. It stays reachable
              from the site footer, which `app/layout.tsx` renders on EVERY page, and from the
              home page's own secondary link row — so this is a demotion, not a removal.
              `home-positioning.spec.ts` pins both halves: absent from the nav, present in the
              footer. */}
          <Link
            href="/about"
            className="hidden text-xs text-gray-500 hover:text-gray-300 transition-colors sm:block"
          >
            About
          </Link>

          {/* NF3.2 fix: `item.public` (e.g. Track Record) only matters once a visitor is INSIDE a
              surface's dropdown — but the whole sub-nav below is itself hidden pre-login
              (`showSubNav`), so a public item was structurally unreachable for a signed-out
              visitor, the exact opposite of the point of marking it public. Render it here
              instead — visible on mobile AND desktop, independent of `showSubNav` — ONLY when
              signed out; a signed-in visitor (entitled or not) already sees it in its normal
              dropdown slot, so this would be a duplicate link once authenticated.

              ⚠️ E9.58: `hidden sm:block`. These used to render at EVERY width, which was fine
              while a logged-out phone showed nothing else — but with a Sign Up button in the bar
              (and the logo at h-12) three surface links overflowed: the wordmark overlapped
              "Rankings" and "Track Record" wrapped onto two lines. They are now in the mobile
              menu below, alongside About and Blog, so nothing became less reachable — more did. */}
          {!showSubNav &&
            publicNavItems().map((item) => (
              <Link
                key={item.key}
                href={item.href}
                className="hidden text-xs text-gray-400 hover:text-gray-200 transition-colors sm:block"
              >
                {item.label}
              </Link>
            ))}

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
            // E9.58 — this whole block used to be `hidden sm:flex`, and the hamburger beside it
            // only renders for a SIGNED-IN user, so a logged-out visitor on a phone had no way to
            // sign in or sign up anywhere in the nav. That was survivable while accounts were
            // invite-only; it is not, now that the inbound path is an indexed locked projection
            // opened on a phone. Sign Up is always visible; Sign In folds away under `sm` so the
            // bar cannot overflow on a small screen (the signup page carries its own "already
            // have an account?" link, so nothing is lost).
            <div className="flex items-center gap-2 sm:gap-3">
              <Button
                variant="ghost"
                size="sm"
                asChild
                className="hidden sm:inline-flex text-gray-400 hover:text-white hover:bg-[#141414]"
              >
                <Link href="/login">Sign In</Link>
              </Button>
              <Button
                size="sm"
                asChild
                className="bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
              >
                {/* was a `mailto:` "Request Access" — signup is self-serve now */}
                <Link href={SIGNUP_HREF}>Sign Up</Link>
              </Button>
            </div>
          )}

          {/* Hamburger — mobile only, now for EVERYONE.
              It used to be `showSubNav &&`, i.e. signed-in only, which left a logged-out visitor
              on a phone with no menu at all: About and Blog are `hidden sm:block`, so they were
              simply unreachable, and the public surfaces had to be crammed into the bar itself. */}
          <button
            className="flex shrink-0 items-center justify-center rounded p-1.5 text-gray-400 hover:text-white hover:bg-[#141414] transition-colors sm:hidden"
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label="Toggle menu"
            aria-expanded={mobileOpen}
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Desktop sub-nav — SPORT-FIRST (E9.45): a dropdown per sport, surfaces within. */}
      {showSubNav && (
        <div className="mx-auto hidden max-w-6xl items-center gap-6 px-4 pb-0 sm:flex">
          {SPORTS.map((sport) => {
            const sportActive = sport.surfaces.some((g) =>
              surfaceItems(g).some((i) => i.key === activeLink),
            )
            return (
              <div key={sport.sport} className="group relative">
                <button
                  className={`flex items-center gap-1 pb-2.5 text-sm transition-colors whitespace-nowrap ${
                    sportActive
                      ? "border-b-2 border-[#10b981] font-medium text-white"
                      : "border-b-2 border-transparent text-gray-500 hover:text-gray-300"
                  }`}
                >
                  {sport.label}
                  <ChevronDown className="h-3 w-3" />
                </button>
                <div className="absolute left-0 top-full z-50 hidden w-56 rounded-md border border-[#262626] bg-[#0f0f0f] py-1 shadow-xl group-hover:block">
                  {visibleSurfaces(sport).map((g) => {
                    const locked = isLocked(g)
                    return (
                      <div key={g.surface} className="py-1">
                        <div className="flex items-center gap-1.5 px-3 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wider text-gray-600">
                          {g.label}
                          {locked && <Lock className="h-3 w-3 text-gray-500" />}
                        </div>
                        {locked ? (
                          <>
                            <Link
                              href="/subscribe"
                              className="flex items-center justify-between px-3 py-2 text-sm text-gray-500 hover:bg-[#1a1a1a] hover:text-gray-300 transition-colors"
                            >
                              <span>Unlock Fantasy</span>
                              <span className="rounded bg-[#10b981]/15 px-1.5 py-0.5 text-[10px] font-semibold text-[#10b981]">
                                Upgrade
                              </span>
                            </Link>
                            {/* NF3.2 — items marked `public` stay reachable even when the surface
                                itself is locked (the past-season track record needs no entitlement). */}
                            {surfaceItems(g).filter((i) => i.public).map((item) => (
                              <Link key={item.key} href={item.href} className={itemClass(item.key)}>
                                {item.label}
                              </Link>
                            ))}
                          </>
                        ) : (
                          g.sections.map((section, si) => (
                            <div key={si}>
                              {section.label && (
                                <div className="px-3 pb-0.5 pt-1.5 text-[10px] font-medium uppercase tracking-wider text-gray-700">
                                  {section.label}
                                </div>
                              )}
                              {visibleItems(section.items).map((item) => (
                                <Link key={item.key} href={item.href} className={itemClass(item.key)}>
                                  {item.label}
                                </Link>
                              ))}
                            </div>
                          ))
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}

          {/* What's New — cross-cutting */}
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
                  <Link key={key} href={href} className={itemClass(key)}>
                    {label}
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Mobile slide-down menu — SIGNED OUT.
          The signed-in menu below is built from SPORTS/`visibleSurfaces`, which is entitlement-
          shaped and wrong for a stranger. This one carries exactly what a logged-out visitor can
          actually reach: the public surfaces, the two marketing pages that were `hidden sm:block`
          and therefore invisible on a phone, and Sign In (Sign Up stays in the bar as the CTA). */}
      {!showSubNav && mobileOpen && (
        <div className="border-t border-[#262626] bg-[#0a0a0a] px-4 py-3 sm:hidden">
          <div className="flex flex-col gap-0.5">
            {publicNavItems().map((item) => (
              <Link
                key={item.key}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className="block whitespace-nowrap rounded-md px-3 py-2.5 text-sm font-medium text-gray-300 hover:bg-[#141414] hover:text-white transition-colors"
              >
                {item.label}
              </Link>
            ))}

            <div className="my-2 border-t border-[#262626]" />

            {/* Written as plain JSX rather than a mapped array on purpose: E9.56c's route guard
                only sees literal `href="/…"` attributes, so a data-driven list would take these
                links OUT of the one check that catches a dead button. */}
            {/* Blog is demoted out of the nav on this viewport too (E9.46) — see the desktop
                comment above. The footer carries it on every page. */}
            <Link
              href="/about"
              onClick={() => setMobileOpen(false)}
              className="block rounded-md px-3 py-2.5 text-sm font-medium text-gray-400 hover:bg-[#141414] hover:text-white transition-colors"
            >
              About
            </Link>

            <div className="my-2 border-t border-[#262626]" />

            <Link
              href="/login"
              onClick={() => setMobileOpen(false)}
              className="block rounded-md px-3 py-2.5 text-sm font-medium text-gray-400 hover:bg-[#141414] hover:text-white transition-colors"
            >
              Sign In
            </Link>
          </div>
        </div>
      )}

      {/* Mobile slide-down menu — SPORT-FIRST */}
      {showSubNav && mobileOpen && (
        <div className="border-t border-[#262626] bg-[#0a0a0a] px-4 py-3 sm:hidden">
          <div className="flex flex-col gap-0.5">
            {SPORTS.map((sport, sportIdx) => (
              // ⚠️ `flex flex-col` is load-bearing, not decoration. A Next.js <Link> renders an <a>,
              // which is INLINE by default, and the mobile item class (unlike the desktop one) has
              // no `block` — so in a plain <div> the items flowed as inline text and wrapped MID-LABEL
              // ("League Board" broke across two lines). Stacking them here fixes every item at once
              // rather than relying on each link's own class.
              <div key={sport.sport} className="flex flex-col">
                {sportIdx > 0 && <div className="my-2 border-t border-[#262626]" />}
                <span className="block px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-600">
                  {sport.label}
                </span>
                {visibleSurfaces(sport).map((g) => {
                  const locked = isLocked(g)
                  if (locked) {
                    return (
                      <div key={g.surface} className="flex flex-col">
                        <Link
                          href="/subscribe"
                          onClick={() => setMobileOpen(false)}
                          className="flex items-center justify-between rounded-md px-3 py-2.5 text-sm font-medium text-gray-400 hover:bg-[#141414] hover:text-white transition-colors"
                        >
                          <span className="flex items-center gap-1.5">
                            <Lock className="h-3.5 w-3.5" /> {g.label} — Unlock
                          </span>
                          <span className="rounded bg-[#10b981]/15 px-1.5 py-0.5 text-[10px] font-semibold text-[#10b981]">
                            Upgrade
                          </span>
                        </Link>
                        {/* NF3.2 — `public` items stay reachable even when the surface is locked. */}
                        {surfaceItems(g).filter((i) => i.public).map((item) => (
                          <Link
                            key={item.key}
                            href={item.href}
                            onClick={() => setMobileOpen(false)}
                            className="block whitespace-nowrap rounded-md px-3 py-2.5 text-sm font-medium text-gray-400 hover:bg-[#141414] hover:text-white transition-colors"
                          >
                            {item.label}
                          </Link>
                        ))}
                      </div>
                    )
                  }
                  return g.sections.flatMap((section) =>
                    visibleItems(section.items).map((item) => (
                      <Link
                        key={item.key}
                        href={item.href}
                        onClick={() => setMobileOpen(false)}
                        className={`block whitespace-nowrap rounded-md px-3 py-2.5 text-sm font-medium transition-colors ${
                          activeLink === item.key
                            ? "bg-[#1a1a1a] text-white"
                            : "text-gray-400 hover:bg-[#141414] hover:text-white"
                        }`}
                      >
                        {item.label}
                      </Link>
                    )),
                  )
                })}
              </div>
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
