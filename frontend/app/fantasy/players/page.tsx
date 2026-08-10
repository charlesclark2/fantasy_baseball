"use client"

// NF3.1 — NFL fantasy Player Search.
//
// FREEMIUM BUILD: PUBLIC (`FantasyPublicGuard`). It is the only way to REACH a player page without
// first finding the player on a board — so gating it while the player pages themselves are free
// would leave the free tier with a door and no handle. It reads exactly one thing,
// `useFantasyProjections`, which is now free for every caller, so there is nothing here that a
// non-entitled visitor cannot have.

import { Nav } from "@/components/nav"
import { FantasyPublicGuard } from "@/components/auth-guard"
import { useAuth } from "@/lib/auth-context"
import { PlayerSearch } from "@/components/fantasy/player-search"

export default function FantasyPlayerSearchPage() {
  const { accessToken, email } = useAuth()
  return (
    <FantasyPublicGuard>
      <div className="min-h-screen bg-[#0a0a0a]">
        {/* `authenticated` is CONDITIONAL — a logged-out visitor needs a Login affordance, not
            signed-in chrome. Mirrors the other public fantasy routes. */}
        <Nav authenticated={!!accessToken} activeLink="fantasy-players" userEmail={email} />
        <PlayerSearch />
      </div>
    </FantasyPublicGuard>
  )
}
