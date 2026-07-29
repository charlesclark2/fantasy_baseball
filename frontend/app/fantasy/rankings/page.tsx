"use client"

// NF3 — NFL fantasy Rankings (browse), format-selectable. Gated by FantasyGuard (E9.45);
// board data loads through the server-side-gated /fantasy/nfl/* endpoints.

import { Nav } from "@/components/nav"
import { FantasyGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { RankingsBoard } from "@/components/fantasy/rankings-board"

export default function FantasyRankingsPage() {
  const { email } = useAuth()
  return (
    <FantasyGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="fantasy-rankings" userEmail={email} />
        <RankingsBoard />
      </div>
    </FantasyGuard>
  )
}
