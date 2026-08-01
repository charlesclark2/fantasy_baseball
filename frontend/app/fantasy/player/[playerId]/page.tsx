"use client"

// NF3.1 — NFL fantasy per-player drill-down. Gated by FantasyGuard, same as the three browse
// surfaces it's linked from (Projections, Rankings, League Board, Draft Optimizer).

import { Nav } from "@/components/nav"
import { FantasyGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { FantasyPlayerPage } from "@/components/fantasy/player-page"

export default function FantasyPlayerRoute() {
  const { email } = useAuth()
  return (
    <FantasyGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated userEmail={email} />
        <FantasyPlayerPage />
      </div>
    </FantasyGuard>
  )
}
