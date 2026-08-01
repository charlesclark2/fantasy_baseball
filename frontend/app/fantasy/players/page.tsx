"use client"

// NF3.1 — NFL fantasy Player Search. Gated by FantasyGuard, same as the four boards it feeds into.

import { Nav } from "@/components/nav"
import { FantasyGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { PlayerSearch } from "@/components/fantasy/player-search"

export default function FantasyPlayerSearchPage() {
  const { email } = useAuth()
  return (
    <FantasyGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        <Nav authenticated activeLink="fantasy-players" userEmail={email} />
        <PlayerSearch />
      </div>
    </FantasyGuard>
  )
}
