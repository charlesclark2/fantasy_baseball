"use client"

// NCAAF-P3.2 — the route. NCAAF is FREE (E9.45), so there is no `AuthGuard` and no
// `SubscriptionGate` here, deliberately and by the same pattern `/fantasy/track-record` uses for
// its public surface: the absence of a guard is the entitlement decision, stated in one place.
//
// ⭐ NCAAF-P3.9 CASHED THAT IN with no edit here, exactly as intended: the key was passed before
// the nav item existed, and adding the item (`nav.tsx`'s `NCAAF_NAV` + `SIGNED_OUT_NAV`) made the
// highlight start working on its own.
//
// ⚠️ THE NAV THIS PAGE ACTUALLY RENDERS IS THE SIGNED-OUT ONE, for most readers. `authenticated`
// is `!!accessToken`, and the surface is free with no guard, so an anonymous visitor is the default
// reader — which is why the door had to be added to `SIGNED_OUT_NAV` and not only to the signed-in
// sport menu, and why the highlight had to be taught to the signed-out bar at all.

import { Nav } from "@/components/nav"
import { useAuth } from "@/lib/auth-context"
import { NcaafGamesPage } from "@/components/ncaaf/games-page"

export default function NcaafGamesRoute() {
  const { accessToken, email } = useAuth()
  return (
    <div className="min-h-screen bg-[#0a0a0a]">
      <Nav authenticated={!!accessToken} activeLink="ncaaf-games" userEmail={email} />
      <NcaafGamesPage />
    </div>
  )
}
