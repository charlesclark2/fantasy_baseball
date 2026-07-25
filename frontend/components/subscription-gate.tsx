"use client"

import { useEffect } from "react"
import { usePathname, useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth-context"
import { PAYWALL_ENABLED, hasEntitlement, isPaidRoute } from "@/lib/paywall"

// App-wide paywall route-guard (E9.8). Mounted once in Providers so the boundary is
// enforced from a single config-driven place (lib/paywall.ts) rather than per-page.
//
// Inert unless NEXT_PUBLIC_PAYWALL_ENABLED=1. When on: a SIGNED-IN user who lacks an
// access group (admin/subscriber/beta_tester) is redirected to /subscribe when they
// land on a paid route. Signed-out users are handled by each page's AuthGuard (→ /login)
// and by /subscribe itself; this gate only acts on the authenticated-but-unentitled case.
export function SubscriptionGate() {
  const { accessToken, groups, loading } = useAuth()
  const pathname = usePathname()
  const router = useRouter()

  useEffect(() => {
    if (!PAYWALL_ENABLED) return
    if (loading) return
    if (!accessToken) return // signed-out → page AuthGuard / login handles it
    if (!pathname || !isPaidRoute(pathname)) return
    if (hasEntitlement(groups)) return
    router.replace("/subscribe")
  }, [accessToken, groups, loading, pathname, router])

  return null
}
