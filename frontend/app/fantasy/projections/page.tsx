"use client"

// NF3 — NFL fantasy Season Projections (browse).
//
// FREEMIUM BUILD: PUBLIC (`FantasyPublicGuard`). This is the free generic board — every
// caller, logged out included, gets the same full payload (`Capability.GENERIC_BOARD`).
// E9.56b made this route public while the server still served it LOCKED; the freemium build
// removed the lock, so what a visitor sees here is the real product rather than an argument
// for buying it. The paid boundary is stated below the board by `FreemiumBoundary`.

import { Nav } from "@/components/nav"
import { FantasyPublicGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { ProjectionsTable } from "@/components/fantasy/projections-table"

export default function FantasyProjectionsPage() {
  const { accessToken, email } = useAuth()
  return (
    <FantasyPublicGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        {/* `authenticated` is now CONDITIONAL — a logged-out visitor needs a Login affordance, not
            signed-in chrome. Mirrors the NF3.2 player route. */}
        <Nav authenticated={!!accessToken} activeLink="fantasy-projections" userEmail={email} />
        <ProjectionsTable />
      </div>
    </FantasyPublicGuard>
  )
}
