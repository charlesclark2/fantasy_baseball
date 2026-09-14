"use client"

// NF-WK-FE1 — the WEEKLY projections route.
//
// FREEMIUM: PUBLIC (`FantasyPublicGuard`), exactly like Projections and Rankings. The two reads
// behind it are `Capability.GENERIC_BOARD` and byte-identical for every caller, so a logged-out
// visitor sees the real product rather than an argument for buying it. The paid boundary is the
// per-row stat line inside the table and the `FreemiumBoundary` beneath it.

import { Nav } from "@/components/nav"
import { FantasyPublicGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { WeeklyProjectionsPage } from "@/components/fantasy/weekly-page"

export default function FantasyWeeklyPage() {
  const { accessToken, email } = useAuth()
  return (
    <FantasyPublicGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        {/* `authenticated` is CONDITIONAL — a logged-out visitor needs a Login affordance, not
            signed-in chrome. Mirrors the NF3.2 player route and the Projections page. */}
        <Nav authenticated={!!accessToken} activeLink="fantasy-weekly" userEmail={email} />
        <WeeklyProjectionsPage />
      </div>
    </FantasyPublicGuard>
  )
}
