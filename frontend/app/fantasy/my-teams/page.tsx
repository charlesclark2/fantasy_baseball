"use client"

// NF-C6 — My Teams (cross-league browse). Gated by FantasyGuard: `subscriber` + `admin` + the
// `fantasy_comp` allow-list (E9.45) — the same gate every other NFL fantasy surface uses. Data comes
// from the server-side-gated /fantasy/nfl/my-teams + /fantasy/nfl/projections endpoints, so the
// client gate is defence in depth rather than the only gate.

import { Nav } from "@/components/nav"
import { FantasyGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { MyTeams } from "@/components/fantasy/my-teams"

export default function FantasyMyTeamsPage() {
  const { email } = useAuth()
  return (
    <FantasyGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="fantasy-my-teams" userEmail={email} />
        <MyTeams />
      </div>
    </FantasyGuard>
  )
}
