"use client"

// NF3 — NFL fantasy League Board / value over replacement (browse), format-selectable. Gated by
// FantasyGuard (E9.45); board data loads through the server-side-gated /fantasy/nfl/* endpoints.

import { Nav } from "@/components/nav"
import { FantasyGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { LeagueBoard } from "@/components/fantasy/league-board"

export default function FantasyLeagueBoardPage() {
  const { email } = useAuth()
  return (
    <FantasyGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="fantasy-league-board" userEmail={email} />
        <LeagueBoard />
      </div>
    </FantasyGuard>
  )
}
