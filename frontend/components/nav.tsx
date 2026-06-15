"use client"

import Image from "next/image"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { LogOut } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/lib/auth-context"

type ActiveLink =
  | "dashboard"
  | "ev-tracker"
  | "performance"
  | "settings"
  | "bet-log"
  | "admin"
  | null

interface NavProps {
  activeLink?: ActiveLink
  authenticated?: boolean
  userEmail?: string | null
}

const SUB_NAV_ITEMS = [
  { label: "Dashboard", href: "/dashboard", key: "dashboard" },
  { label: "EV Tracker", href: "/ev-tracker", key: "ev-tracker" },
  { label: "Performance", href: "/performance", key: "performance" },
  { label: "Bet Log", href: "/bet-log", key: "bet-log" },
] as const

export function Nav({
  activeLink = null,
  authenticated = false,
  userEmail,
}: NavProps) {
  const { accessToken, signOut } = useAuth()
  const router = useRouter()
  const isSignedIn = !!accessToken

  return (
    <nav className="sticky top-0 z-50 border-b border-[#262626] bg-[#0a0a0a]/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        {/* Logo */}
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

        {/* Right actions */}
        <div className="flex items-center gap-3">
          {authenticated ? (
            <>
              <span className="hidden text-xs text-gray-500 sm:block">
                {userEmail ?? "—"}
              </span>
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
            </>
          ) : isSignedIn ? (
            <Button
              size="sm"
              asChild
              className="bg-[#10b981] text-[#0a0a0a] font-semibold hover:bg-[#059669]"
            >
              <Link href="/dashboard">Dashboard</Link>
            </Button>
          ) : (
            <>
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
                <a href="mailto:charlie@credencesports.com?subject=Beta%20Access%20Request">Request Access</a>
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Sub-nav — authenticated only */}
      {authenticated && (
        <div className="mx-auto flex max-w-6xl gap-6 overflow-x-auto px-4 pb-0">
          {SUB_NAV_ITEMS.map(({ label, href, key }) => (
            <Link
              key={key}
              href={href}
              className={
                activeLink === key
                  ? "border-b-2 border-[#10b981] pb-2.5 text-sm text-white font-medium transition-colors"
                  : "border-b-2 border-transparent pb-2.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
              }
            >
              {label}
            </Link>
          ))}
          {activeLink === "admin" && (
            <Link
              href="/admin"
              className="border-b-2 border-[#10b981] pb-2.5 text-sm text-white font-medium transition-colors"
            >
              Admin
            </Link>
          )}
        </div>
      )}
    </nav>
  )
}
