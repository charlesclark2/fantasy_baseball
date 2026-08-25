"use client"

// NCAAF-P3.2 — the route. NCAAF is FREE (E9.45), so there is no `AuthGuard` and no
// `SubscriptionGate` here, deliberately and by the same pattern `/fantasy/track-record` uses for
// its public surface: the absence of a guard is the entitlement decision, stated in one place.
//
// ⚠️ `activeLink` is passed but NCAAF is not in the nav yet — that is NCAAF-P3.9's story (slot the
// vertical into E9.45's sport-first nav). Passing the key now means the highlight starts working
// the moment P3.9 adds the item, with no edit here.

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
