"use client"

// NF3 — NFL fantasy Rankings (browse), format-selectable.
//
// FREEMIUM BUILD: PUBLIC (`FantasyPublicGuard`). This is the free generic board — every
// caller, logged out included, gets the same full payload (`Capability.GENERIC_BOARD`).
// E9.56b made this route public while the server still served it LOCKED; the freemium build
// removed the lock, so what a visitor sees here is the real product rather than an argument
// for buying it. The paid boundary is stated below the board by `FreemiumBoundary`.

import { Nav } from "@/components/nav"
import { FantasyPublicGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { RankingsBoard } from "@/components/fantasy/rankings-board"
import { LandingView } from "@/components/analytics/landing-view"
import { ACQUISITION_SURFACES } from "@/lib/funnel-telemetry"

export default function FantasyRankingsPage() {
  const { accessToken, email } = useAuth()
  return (
    <FantasyPublicGuard>
      {/* G100-D0 — an acquisition surface: the free board is the value a stranger comes for. */}
      <LandingView surface={ACQUISITION_SURFACES.FANTASY_RANKINGS} />
      <div className="min-h-screen bg-[#0a0a0a]">
        {/* `authenticated` is now CONDITIONAL — a logged-out visitor needs a Login affordance, not
            signed-in chrome. Mirrors the NF3.2 player route. */}
        <Nav authenticated={!!accessToken} activeLink="fantasy-rankings" userEmail={email} />
        <RankingsBoard />
      </div>
    </FantasyPublicGuard>
  )
}
